#!/usr/bin/env python2

import pygtk
pygtk.require('2.0')
import gtk
import gobject

import os
import os.path
import csv
import ConfigParser
from subprocess import Popen, PIPE, STDOUT


class TextComboBox(object):
    """Simple one-column text combobox."""

    def __init__(self, combobox):
        self.combobox = combobox
        liststore = gtk.ListStore(gobject.TYPE_STRING)
        self.combobox.set_model(liststore)
        cell_renderer = gtk.CellRendererText()
        self.combobox.pack_start(cell_renderer, True)
        self.combobox.add_attribute(cell_renderer, 'text', 0)

    def __getattr__(self, attr):
        """Delegate calls to undefined attributes to the combobox."""

        return getattr(self.combobox, attr)

    def clear(self):
        """Shortcut method to delete all items from the combobox."""

        return self.combobox.get_model().clear()

    def index(self, value):
        """Find the value's position (0-based) in the combobox."""

        value_idx = None
        for idx, row in enumerate(self.combobox.get_model()):
            if row[0] == value:
                value_idx = idx

        if value_idx is None:
            raise ValueError

        return value_idx

    def set_active_text(self, text):
        text_idx = self.index(text)
        self.combobox.set_active(text_idx)


class InputFileChooser(gtk.FileChooserDialog):
    def __init__(self, title, parent):
        buttons = (
            gtk.STOCK_OK, gtk.RESPONSE_ACCEPT,
            gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
        )
        gtk.FileChooserDialog.__init__(self, title, parent, gtk.DIALOG_MODAL, buttons)
        self.set_action(gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)


class OutputFileChooser(gtk.FileChooserDialog):
    def __init__(self, title, parent):
        buttons = (
            gtk.STOCK_OK, gtk.RESPONSE_ACCEPT,
            gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
        )
        gtk.FileChooserDialog.__init__(self, title, parent, gtk.DIALOG_MODAL, buttons)
        self.set_action(gtk.FILE_CHOOSER_ACTION_SAVE)
        self.set_do_overwrite_confirmation(True)


class ParaminatorGUI(object):
    def __init__(self):
        self.profile_directory = None
        self.profile_file = None
        self.parameter = None
        self.output_file = None

        self.builder = gtk.Builder()
        self.builder.add_from_file('paraminator.glade')

        self.window = self.builder.get_object('window_main')
        self.entry_input = self.builder.get_object('entry_input')
        self.button_exit = self.builder.get_object('button_exit')
        self.button_browse_input = self.builder.get_object('button_browse_input')
        self.combobox_profile_file = TextComboBox(self.builder.get_object('combobox_profile_file'))
        self.combobox_parameter = TextComboBox(self.builder.get_object('combobox_parameter'))
        self.button_browse_output = self.builder.get_object('button_browse_output')
        self.button_generate = self.builder.get_object('button_generate')
        self.spinbutton_start = self.builder.get_object('spinbutton_start')
        self.spinbutton_end = self.builder.get_object('spinbutton_end')
        self.spinbutton_increment = self.builder.get_object('spinbutton_increment')
        self.entry_output = self.builder.get_object('entry_output')
        self.textview_output = self.builder.get_object('textview_output')

        signals = {
            'on_window_main_destroy': self.on_window_main_destroy,
            'on_button_exit_clicked': self.on_button_exit_clicked,
            'on_button_browse_input_clicked': self.on_button_browse_input_clicked,
            'on_combobox_profile_file_changed': self.on_combobox_profile_file_changed,
            'on_combobox_parameter_changed': self.on_combobox_parameter_changed,
            'on_button_browse_output_clicked': self.on_button_browse_output_clicked,
            'on_button_generate_clicked': self.on_button_generate_clicked,
            'on_spinbutton_start_value_changed': self.on_spinbutton_start_value_changed,
            'on_spinbutton_end_value_changed': self.on_spinbutton_end_value_changed,
            'on_spinbutton_increment_value_changed': self.on_spinbutton_increment_value_changed,
        }
        self.builder.connect_signals(signals)

        self.config = ConfigParser.RawConfigParser()
        self.read_config()

        # run validate to set errors on the generate button to explain why it's disabled
        self.validate()

    def find_files(self, directory):
        """Traverse the profile directory and find profile files to tweak."""

        profile_files = []
        for root, dirs, files in os.walk(directory):
            for name in files:
                if name.lower().endswith('.csv'):
                    relative_path = os.path.join(root, name)[len(directory):]
                    if relative_path.startswith(os.path.sep):
                        relative_path = relative_path[1:]
                    profile_files.append(relative_path)
        return profile_files

    def find_params(self, filename):
        """List parameters in a profile file."""

        reader = csv.reader(open(filename, 'rb'), delimiter="\t")
        params = []
        for row in reader:
            params.append(row[0])
        return params

    def set_profile_directory(self, directory):
        self.profile_directory = directory
        self.entry_input.set_text(self.profile_directory)
        self.combobox_profile_file.clear()
        self.combobox_parameter.clear()

        # find profile files in the directory and add them to profile combobox
        try:
            profile_files = self.find_files(self.profile_directory)
            if profile_files:
                profile_files.sort()
                for name in profile_files:
                    self.combobox_profile_file.append_text(name)
        except IOError:
            # directory does not exist or is not readable
            self.profile_directory = None
            self.entry_input.set_text('')

    def set_profile_file(self, profile_file):
        self.profile_file = profile_file
        self.combobox_parameter.clear()

        try:
            params = self.find_params(os.path.join(self.profile_directory, self.profile_file))
            if params:
                params.sort()
                for param in params:
                    self.combobox_parameter.append_text(param)
        except IOError:
            # file does not exist or is not readable
            self.profile_file = None

    ### Config file handling {{{

    def read_config(self):
        """Load previously saved configuration from file."""

        def read_profile_directory(section, key, value):
            if value:
                self.set_profile_directory(value)

        def read_profile_file(section, key, value):
            if value:
                self.set_profile_file(value)
                try:
                    self.combobox_profile_file.set_active_text(self.profile_file)
                except ValueError:
                    pass

        def read_parameter(section, key, value):
            if value:
                self.parameter = value
                try:
                    self.combobox_parameter.set_active_text(self.parameter)
                except ValueError:
                    pass

        def read_output_file(section, key, value):
            if value:
                self.output_file = value
                self.entry_output.set_text(self.output_file)

        def read_paraminator_path(section, key, value):
            if value:
                self.paraminator_path = value
            else:
                default_paraminator_path(section, key)

        def default_paraminator_path(section, key):
            self.paraminator_path = 'paraminator.py'

        def read_python_path(section, key, value):
            if value:
                self.python_path = value
            else:
                default_python_path(section, key)

        def default_python_path(section, key):
            self.python_path = 'python2'
        

        self.config.read('paraminatorgui.ini')

        config_map = {
            'ParaminatorParameters': [
                ('profile_directory', read_profile_directory, None),
                ('profile_file', read_profile_file, None),
                ('parameter', read_parameter, None),
                ('output_file', read_output_file, None),
            ],
            'config': [
                ('paraminator_path', read_paraminator_path, default_paraminator_path),
                ('python_path', read_python_path, default_python_path),
            ],
        }

        for section in config_map.keys():
            for key, handler, default in config_map[section]:
                try:
                    handler(section, key, self.config.get(section, key))
                except ConfigParser.Error:
                    if default:
                        default(section, key)

    def write_config(self):
        """Save application configuration to a file."""

        section = 'ParaminatorParameters'
        if not self.config.has_section(section):
            self.config.add_section(section)

        self.config.set(section, 'profile_directory', self.profile_directory or '')
        self.config.set(section, 'profile_file', self.profile_file or '')
        self.config.set(section, 'parameter', self.parameter or '')
        self.config.set(section, 'output_file', self.output_file or '')
        self.config.set(section, 'start', self.spinbutton_start.get_value() or '')
        self.config.set(section, 'end', self.spinbutton_end.get_value() or '')
        self.config.set(section, 'increment', self.spinbutton_increment.get_value() or '')

        config_section= 'config'
        if not self.config.has_section(config_section):
            self.config.add_section(config_section)

        self.config.set(config_section, 'paraminator_path', self.paraminator_path or '')
        self.config.set(config_section, 'python_path', self.python_path or '')

        with open('paraminatorgui.ini', 'wb') as config_file:
            self.config.write(config_file)

    # end Config file handling }}}

    ### Signal handlers {{{

    def on_window_main_destroy(self, widget):
        self._quit()

    def on_button_exit_clicked(self, widget):
        self._quit()

    def _quit(self):
        self.write_config()
        gtk.main_quit()

    def on_button_browse_input_clicked(self, widget):
        """Show a dialog to select a profile directory."""

        dialog = InputFileChooser('Select profile directory', self.window)
        if self.profile_directory:
            dialog.set_filename(self.profile_directory)
        response = dialog.run()
        if response == gtk.RESPONSE_ACCEPT:
            self.set_profile_directory(dialog.get_filename())
        dialog.destroy()
        self.validate()

    def on_combobox_profile_file_changed(self, widget):
        """Find parameters names in the selected profile file and add them to param combobox."""

        profile_file = self.combobox_profile_file.get_active_text()
        if profile_file:
            self.set_profile_file(profile_file)
            self.validate()

    def on_combobox_parameter_changed(self, widget):
        self.parameter = self.combobox_parameter.get_active_text()
        if self.parameter:
            self.validate()

    def on_button_browse_output_clicked(self, widget):
        dialog = OutputFileChooser('Select output file', self.window)
        if self.output_file:
            dialog.set_filename(self.output_file)
        if dialog.run() == gtk.RESPONSE_ACCEPT:
            self.output_file = dialog.get_filename()
            self.entry_output.set_text(self.output_file)
        dialog.destroy()
        self.validate()

    def on_button_generate_clicked(self, widget):
        filename = os.path.join(self.profile_directory, self.profile_file)

        start = self.spinbutton_start.get_value()
        end = self.spinbutton_end.get_value()
        increment = self.spinbutton_increment.get_value()
        if self.parameter.endswith(':'):
            parameter = self.parameter[:-1]
        else:
            parameter = self.parameter

        # prepare the ui
        self.button_generate.set_sensitive(False)
        self.button_exit.set_sensitive(False)
        buff = gtk.TextBuffer()
        self.textview_output.set_buffer(buff)
        self.textview_output.set_sensitive(True)
        iterator = buff.get_end_iter()

        command = [
            self.python_path,
            self.paraminator_path,
            '--file=%s' % filename,
            '--parameter=%s' % parameter,
            '--start=%s' % start,
            '--end=%s' % end,
            '--increment=%s' % increment,
            '--output=%s' % self.output_file,
        ]
        p = Popen(command, stdout=PIPE, stderr=STDOUT)
        while True:
            line = p.stdout.readline()
            if not line:
                break
            buff.insert(iterator, line)
            self.textview_output.scroll_to_iter(iterator, 0)
            # keep the ui responsive
            while gtk.events_pending():
                gtk.main_iteration(False)

        self.button_generate.set_sensitive(True)
        self.button_exit.set_sensitive(True)

    def on_spinbutton_start_value_changed(self, widget):
        self.validate()

    def on_spinbutton_end_value_changed(self, widget):
        self.validate()

    def on_spinbutton_increment_value_changed(self, widget):
        self.validate()

    # end Signal handlers }}}

    ### Validation {{{

    def validate(self):
        """Validate user inputs and enable/disable the Generate button accordingly."""

        errors = []
        validators = [
            '_valid_directory_input',
            '_valid_profile_file',
            '_valid_parameter',
            '_valid_start',
            '_valid_end',
            '_valid_increment',
            '_valid_output',
        ]
        everything_ok = reduce(lambda x, y: x and y, [getattr(self, v)(errors) for v in validators])
        if everything_ok:
            self.button_generate.set_sensitive(True)
            self.button_generate.set_has_tooltip(False)
        else:
            self.button_generate.set_sensitive(False)
            self.add_errors_tooltip(errors)

    def add_errors_tooltip(self, errors):
        """Display validation errors as a Generate button tooltip."""

        self.button_generate.set_tooltip_text("\n".join(errors))

    def _valid_directory_input(self, errors):
        valid = True
        if not self.profile_directory:
            errors.append('Please choose a profile directory')
            valid = False
        elif not os.path.exists(self.profile_directory):
            errors.append('Profile directory does not exist on disk')
            valid = False

        return valid

    def _valid_profile_file(self, errors):
        valid = True
        if not self.profile_file:
            errors.append('Please choose a profile file')
            valid = False
        elif not os.path.exists(os.path.join(self.profile_directory, self.profile_file)):
            errors.append('Profile file does not exist on disk')

        return valid

    def _valid_parameter(self, errors):
        valid = True
        if not self.parameter:
            errors.append('Please select a parameter to tweak')
            valid = False

        return valid

    def _valid_start(self, errors):
        return True

    def _valid_end(self, errors):
        valid = True
        if self.spinbutton_start.get_value() > self.spinbutton_end.get_value():
            errors.append('Ending value cannot be less than the starting value')
            valid = False
        
        return valid

    def _valid_increment(self, errors):
        valid = True
        if self.spinbutton_increment.get_value() <= 0:
            errors.append('Increment should be greater than 0 (zero)')
            valid = False

        return valid

    def _valid_output(self, errors):
        valid = True
        if not self.output_file:
            errors.append('Please set an output file')
            valid = False

        return valid

    # end Validation }}}


if __name__ == '__main__':
    app = ParaminatorGUI()
    app.window.show()
    gtk.main()
