# autolatex - __init__.py
# Copyright (C) 2013  Stephane Galland <galland@arakhne.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

#---------------------------------
# IMPORTS
#---------------------------------

# Import standard python libs
import os
import subprocess
import tempfile
import re
# Try to use the threading library if it is available
try:
    import threading as _threading
except ImportError:
    import dummy_threading as _threading
# Include the Glib, Gtk and Gedit libraries
from gi.repository import GObject, Gtk, Gio, GdkPixbuf, Gedit, PeasGtk

# AutoLaTeX internal libs
import autolatex_utils as utils
import autolatex_config_window as config_window
import autolatex_gsettings as gsettings
import autolatex_plugin_config as plugin_config

#---------------------------------
# INTERNATIONALIZATION
#---------------------------------

import gettext
_T = gettext.gettext
utils.init_internationalization()

#---------------------------------
# DEFINITION OF THE GTK CONTRIBUTIONS
#---------------------------------
UI_XML = """<ui>
<menubar name="MenuBar">
    <menu name="ToolsMenu" action="Tools">
      <placeholder name="ToolsOps_3">
	<menu action="AutoLaTeXMenu">
	  <menuitem action="AutoLaTeXGenerateImageAction"/>
	  <menuitem action="AutoLaTeXCompileAction"/>
	  <menuitem action="AutoLaTeXCleanAction"/>
	  <menuitem action="AutoLaTeXCleanallAction"/>
	  <menu action="AutoLaTeXSyncTeXMenu">
	    <menuitem action="AutoLaTeXEnableSyncTeXAction"/>
	    <menuitem action="AutoLaTeXUpdateForSyncTeXAction"/>
            <placeholder name="AutoLaTeXSyncTeXOps"/>
          </menu>
          <placeholder name="AutoLaTeXCompileOps"/>
	  <separator />
	  <menuitem action="AutoLaTeXViewAction"/>
          <placeholder name="AutoLaTeXViewOps"/>
	  <separator />
	  <menuitem action="AutoLaTeXMakeFlatAction"/>
          <placeholder name="AutoLaTeXExportOps"/>
	  <separator />
	  <menu action="AutoLaTeXConfigMenu">
	    <menuitem action="AutoLaTeXDocumentConfAction"/>
	    <menuitem action="AutoLaTeXRemoveDocumentConfAction"/>
	    <separator />
	    <menuitem action="AutoLaTeXUserConfAction"/>
	    <menuitem action="AutoLaTeXRemoveUserConfAction"/>
            <placeholder name="AutoLaTeXConfigOps"/>
          </menu>
        </menu>
      </placeholder>
    </menu>
</menubar>
<toolbar name="ToolBar">
    <placeholder name="AutoLaTeX_toolbar">
        <separator/>
        <toolitem action="AutoLaTeXCompileAction"/>
        <toolitem action="AutoLaTeXCleanAction"/>
        <toolitem action="AutoLaTeXViewAction"/>
    </placeholder>
</toolbar>
</ui>"""

#---------------------------------
# CLASS AutoLaTeXExecutionThread
#---------------------------------

# Launch AutoLaTeX inside a thread, and wait for the result
class AutoLaTeXExecutionThread(_threading.Thread):
    # caller is an instance of AutoLaTeXPlugin
    # directory is the path to set as the current path
    # directive is the AutoLaTeX command
    # params are the CLI options for AutoLaTeX
    def __init__(self, caller, directory, directive, params):
	_threading.Thread.__init__(self)
	self.daemon = True
	self._caller = caller
	self._directory = directory
	self._cmd = [utils.AUTOLATEX_BINARY] + params
	if directive:
		self._cmd.append(directive);

    # Run the thread
    def run(self):
	os.chdir(self._directory)
	process = subprocess.Popen(self._cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	output = ''
	if process:
	    out, err = process.communicate()
	    retcode = process.returncode
	    if retcode != 0:
		output = out + err
	# Update the UI for the inside of the Gtk thread
	GObject.idle_add(self._caller._update_action_validity, True, output)

#---------------------------------
# CLASS AutoLaTeXPlugin
#---------------------------------

# Plugin for Gedit
class AutoLaTeXPlugin(GObject.Object, Gedit.WindowActivatable, PeasGtk.Configurable):
    __gtype_name__ = "AutoLaTeXPlugin"
    window = GObject.property(type=Gedit.Window)
    
    #Constructor
    def __init__(self):
        GObject.Object.__init__(self)
	self._compilation_under_progress = False # Indicate if the compilation is under progress
	self._console_icon = None # Icon of the error console
	self._error_console = None # Current instance of the error console
	self._gsettings = gsettings.Manager()
	self._syntex_regex = re.compile('\%.*mainfile:\s*(.*)$')

    # Invoked when the configuration window is open
    def do_create_configure_widget(self):
        return plugin_config.Panel(self._gsettings, self.window)

    # Invoked when the plugin is activated 
    def do_activate(self):
	self._console_icon = self._get_icon('console')
	if not self._gsettings:
		self._gsettings = gsettings.Manager()
        self._add_ui()
	self._check_autolatex_binaries()

    # Invoke when the plugin is desactivated
    def do_deactivate(self):
        self._remove_ui()
	self._gsettings.unbind()
	self._gsettings = None

    # Check if the AutoLaTeX binaries were found
    def _check_autolatex_binaries(self):
	if not utils.AUTOLATEX_BINARY and not utils.AUTOLATEX_BACKEND_BINARY:
		dialog = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _T("The programs 'autolatex' and 'autolatex-backend'\nwere not found.\nPlease fix the configuration of the AutoLaTeX plugin."))
		answer = dialog.run()
		dialog.destroy()
	elif not utils.AUTOLATEX_BINARY:
		dialog = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _T("The program 'autolatex' was not found.\nPlease fix the configuration of the AutoLaTeX plugin."))
		answer = dialog.run()
		dialog.destroy()
	elif not utils.AUTOLATEX_BACKEND_BINARY:
		dialog = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, _T("The program 'autolatex-backend' was not found.\nPlease fix the configuration of the AutoLaTeX plugin."))
		answer = dialog.run()
		dialog.destroy()

    # Invoke when the UI is updated
    def do_update_state(self):
	directory = self._find_AutoLaTeX_dir()
	hasTeXDocument = self._is_TeX_document()
	hasAutoLaTeXDocument = (directory!=None)
	isInTeXContext = (hasTeXDocument or hasAutoLaTeXDocument)
	# Display or hide the menus
	self._menu.set_visible(isInTeXContext)
	self._document_actions.set_visible(isInTeXContext)
	self._texsensitive_actions.set_visible(isInTeXContext)
	self._general_actions.set_visible(isInTeXContext)
	# Test if the current document is inside a TeX context.
	if isInTeXContext:
		if directory:
			cfgFile = os.path.join(directory, '.autolatex_project.cfg')
			hasDocConfFile = os.path.exists(cfgFile)
		else:
			hasDocConfFile = False
		hasUserConfFile = os.path.exists(os.path.join(os.path.expanduser("~"), '.autolatex'))
		# Change the sensitivity
		if self._document_actions:
		    self._document_actions.set_sensitive(hasAutoLaTeXDocument
				and not self._compilation_under_progress)
		if self._texsensitive_actions:
		    self._texsensitive_actions.set_sensitive(hasTeXDocument
				and not self._compilation_under_progress)
		if self._docconfsensitive_actions:
		    self._docconfsensitive_actions.set_sensitive(hasDocConfFile
				and not self._compilation_under_progress)
		if self._userconfsensitive_actions:
		    self._userconfsensitive_actions.set_sensitive(hasUserConfFile
				and not self._compilation_under_progress)
		
    # Update the UI according to the flag "compilation under progress"
    # and to compilation outputs
    def _update_action_validity(self, valid, console_content):
	# Display or hide the error console if an error message is given or not
	if (console_content):
		if (not self._error_console or self._error_console.get_parent == None):
			if (not self._error_console):
				self._error_console = Gtk.TextView()
				self._error_console.set_editable(False)
				self._error_console.set_hscroll_policy(Gtk.ScrollablePolicy.NATURAL)
				self._error_console.set_vscroll_policy(Gtk.ScrollablePolicy.NATURAL)
			panel = self.window.get_bottom_panel()
			panel.add_item(self._error_console,
				"autolatex-console-panel",
				_T("AutoLaTeX Console"),
				Gtk.Image.new_from_pixbuf(self._console_icon))
		self._error_console.get_buffer().set_text(console_content)
	        panel.activate_item(self._error_console)
		if panel.get_property("visible") == False:
                        panel.set_property("visible", True)
	else:
		if (self._error_console):
			panel = self.window.get_bottom_panel()
			panel.remove_item(self._error_console)
			self._error_console = None
	# Update the sensitivities of the Widgets
	self._compilation_under_progress = not valid
	self.do_update_state()    

    # Load an icon from the AutoLaTeX package
    def _get_icon(self, icon):
	return GdkPixbuf.Pixbuf.new_from_file(utils.make_toolbar_icon_path('autolatex-'+icon+'.png'))


    # Add any contribution to the Gtk UI
    def _add_ui(self):
	# Get the UI manager
        manager = self.window.get_ui_manager()
	# Create the Top menu for AutoLaTeX
        self._menu = Gtk.ActionGroup("AutoLaTeXMenu")
        self._menu.add_actions([
            ('AutoLaTeXMenu', None, _T("AutoLaTeX"), 
                None, _T("AutoLaTeX"), 
                None),
        ])
        manager.insert_action_group(self._menu)
	# Create the menu for SyncTeX
        self._synctex_menu = Gtk.ActionGroup("AutoLaTeXSyncTeXMenu")
        self._synctex_menu.add_actions([
            ('AutoLaTeXSyncTeXMenu', Gtk.STOCK_DISCONNECT, _T("SyncTeX"), 
                None, _T("SyncTeX"), 
                None),
        ])
	manager.insert_action_group(self._synctex_menu)
	# Create the menu for Configurations
        self._synctex_menu = Gtk.ActionGroup("AutoLaTeXConfigMenu")
        self._synctex_menu.add_actions([
            ('AutoLaTeXConfigMenu', None, _T("Configuration"), 
                None, _T("Configuration of the AutoLaTeX processes"), 
                None),
        ])
	manager.insert_action_group(self._synctex_menu)
	# Create the group of actions that are needing an AutoLaTeX document
        self._document_actions = Gtk.ActionGroup("AutoLaTeXDocumentActions")
        self._document_actions.add_actions([
	    ('AutoLaTeXGenerateImageAction', None, _T("Generate images"), 
                None, _T("Generate the images with AutoLaTeX"), 
                self.on_generateimage_action_activate),
            ('AutoLaTeXCompileAction', None, _T("Compile"), 
                '<shift><ctrl>R', _T("Compile with AutoLaTeX"), 
                self.on_compile_action_activate),
            ('AutoLaTeXCleanAction', None, _T("Remove temporary files"), 
                None, _T("Clean with AutoLaTeX"), 
                self.on_clean_action_activate),
            ('AutoLaTeXCleanallAction', None, _T("Clean all"), 
                '<shift><ctrl>C', _T("Clean all with AutoLaTeX"), 
                self.on_cleanall_action_activate),
            ('AutoLaTeXViewAction', None, _T("View the PDF"), 
                None, _T("Open the PDF viewer"), 
                self.on_view_action_activate),
            ('AutoLaTeXMakeFlatAction', None, _T("Create flat version"), 
                None, _T("Create a flat version of the document, to be submitted to on-line publication systems (Elsevier...)"), 
                self.on_makeflat_action_activate),
        ])
        manager.insert_action_group(self._document_actions)
	# Create the group of actions that are needing an TeX document
        self._texsensitive_actions = Gtk.ActionGroup("AutoLaTeXTeXSensitiveActions")
        self._texsensitive_actions.add_actions([
            ('AutoLaTeXDocumentConfAction', None, _T("Document configuration"), 
                None, _T("Change the configuration for the document"), 
                self.on_document_configuration_action_activate),
        ])
        manager.insert_action_group(self._texsensitive_actions)
	# Create the group of actions that are needing the configuration file of a document
        self._docconfsensitive_actions = Gtk.ActionGroup("AutoLaTeXDocConfSensitiveActions")
        self._docconfsensitive_actions.add_actions([
            ('AutoLaTeXRemoveDocumentConfAction', None, _T("Delete document configuration"), 
                None, _T("Delete the configuration for the document"), 
                self.on_delete_document_configuration_action_activate),
        ])
        manager.insert_action_group(self._docconfsensitive_actions)
	# Create the group of actions that are needing the configuration file of the user
        self._userconfsensitive_actions = Gtk.ActionGroup("AutoLaTeXUserConfSensitiveActions")
        self._userconfsensitive_actions.add_actions([
            ('AutoLaTeXRemoveUserConfAction', None, _T("Delete user configuration"), 
                None, _T("Delete the configuration for the user"), 
                self.on_delete_user_configuration_action_activate),
        ])
        manager.insert_action_group(self._userconfsensitive_actions)
	# Create the group of actions that are not needing any special document
        self._general_actions = Gtk.ActionGroup("AutoLaTeXGeneralActions")
        self._general_actions.add_toggle_actions([
            ('AutoLaTeXEnableSyncTeXAction', None, _T("Force the use of SyncTeX"), 
                None, _T("Use SyncTeX even if the document and user configurations say 'no'"), 
                self.on_enable_synctex_action_activate),
	])
        self._general_actions.add_actions([
            ('AutoLaTeXUpdateForSyncTeXAction', None, _T("Update TeX file with SyncTeX reference"), 
                None, _T("Update the text of the TeX file to add the reference to the main document"), 
                self.on_update_for_synctex_action_activate),
            ('AutoLaTeXUserConfAction', None, _T("User configuration"), 
                None, _T("Change the configuration for the user"), 
                self.on_user_configuration_action_activate),
        ])
        manager.insert_action_group(self._general_actions)
	# Put the icons into the actions
	for definition in [	(self._document_actions, 'AutoLaTeXGenerateImageAction', 'images'),
				(self._document_actions, 'AutoLaTeXCompileAction', 'compile'),
				(self._document_actions, 'AutoLaTeXCleanAction', 'clean'),
				(self._document_actions, 'AutoLaTeXCleanallAction', 'cleanall'),
				(self._document_actions, 'AutoLaTeXViewAction', 'view'),
				(self._texsensitive_actions, 'AutoLaTeXDocumentConfAction', 'preferences'),
				(self._general_actions, 'AutoLaTeXUserConfAction', 'preferences')
			]:
		action = definition[0].get_action(definition[1])
		action.set_gicon(self._get_icon(definition[2]))
	# Add the Gtk contributions
        self._ui_merge_id = manager.add_ui_from_string(UI_XML)
        manager.ensure_update()
	# Change the state of the check-boxes
	checkbox = self._general_actions.get_action('AutoLaTeXEnableSyncTeXAction')
	checkbox.set_active(self._gsettings.get_force_synctex())
	# Connect from gsettings
	self._gsettings.connect('force-synctex', self.on_gsettings_changed)

    # Remove all contributions to the Gtk UI
    def _remove_ui(self):
	# Disconnect from gsettings
	self._gsettings.disconnect('force-synctex')
	# Remove the error console
	if (self._error_console):
		panel = self.window.get_bottom_panel()
		panel.remove_item(self._error_console)
		self._error_console = None
	# Remove the Gtk Widgets
        manager = self.window.get_ui_manager()
        manager.remove_ui(self._ui_merge_id)
        manager.remove_action_group(self._document_actions)
        manager.remove_action_group(self._texsensitive_actions)
        manager.remove_action_group(self._docconfsensitive_actions)
        manager.remove_action_group(self._userconfsensitive_actions)
        manager.remove_action_group(self._general_actions)
	manager.remove_action_group(self._synctex_menu)
        manager.remove_action_group(self._menu)
        manager.ensure_update()
    
    # Test if a given string is a standard extension for TeX document
    def _is_TeX_extension(self, ext):
	ext = ext.lower()
	if ext == '.tex' or ext =='.latex':
	    return True
	else:
	    return False

    # Replies if the active document is a TeX document
    def _is_TeX_document(self):
        doc = self.window.get_active_document()
        if doc:
            doc = Gedit.Document.get_location(doc)
	    if doc:
		ext = os.path.splitext(doc.get_path())[-1]
		return self._is_TeX_extension(ext)
        return False

    # Try to find the directory where an AutoLaTeX configuration file is
    # located. The search is traversing the parent directory from the current
    # document.
    def _find_AutoLaTeX_dir(self):
        adir = None
        doc = self.window.get_active_document()
        if doc:
            doc = Gedit.Document.get_location(doc)
	    if doc:
		document_name = doc.get_path()
                curdir = Gio.File.new_for_path(os.getcwd())
                doc = doc.get_parent()
		doc = curdir.resolve_relative_path(doc.get_path())
                doc = doc.get_path()
		document_dir = doc
                cfgFile = os.path.join(doc,".autolatex_project.cfg")
                rootFile = os.path.join('/',".autolatex_project.cfg")
	        while rootFile != cfgFile and not os.path.exists(cfgFile):
		    doc = os.path.dirname(doc)
                    cfgFile = os.path.join(doc,".autolatex_project.cfg")

                if rootFile != cfgFile:
                    adir = os.path.dirname(cfgFile)
		else:
		    ext = os.path.splitext(document_name)[-1]
		    if self._is_TeX_extension(ext):
		        adir = document_dir

	return adir

    def _launch_AutoLaTeX(self, directive, params):
	directory = self._find_AutoLaTeX_dir()
	if directory:
	    GObject.idle_add(self._update_action_validity, False, None)
	    thread = AutoLaTeXExecutionThread(self, directory, directive, params)
	    thread.start()

    def _apply_general_autolatex_cli_options(self, params):
	if self._gsettings.get_force_synctex():
		params = [ '--synctex' ] + params
	params = [ utils.DEFAULT_LOG_LEVEL ] + params
	return params

    def on_clean_action_activate(self, action, data=None):
	self._launch_AutoLaTeX('clean', self._apply_general_autolatex_cli_options(
			[ '--noview' ]))

    def on_cleanall_action_activate(self, action, data=None):
	self._launch_AutoLaTeX('cleanall', self._apply_general_autolatex_cli_options(
			[ '--noview' ]))

    def on_compile_action_activate(self, action, data=None):
	self._launch_AutoLaTeX('all', self._apply_general_autolatex_cli_options(
			[ '--noview' ]))

    def on_generateimage_action_activate(self, action, data=None):
	self._launch_AutoLaTeX('images', self._apply_general_autolatex_cli_options(
			[ '--noview' ]))

    def on_view_action_activate(self, action, data=None):
	self._launch_AutoLaTeX('view', self._apply_general_autolatex_cli_options(
			[ '--asyncview' ]))

    def on_document_configuration_action_activate(self, action, data=None):
	directory = self._find_AutoLaTeX_dir()
	if directory:
		cfgFile = os.path.join(directory,".autolatex_project.cfg")
		runConfig = True
		if not os.path.exists(cfgFile):
			dialog = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, _T("Do you want to create a configuration\nfile for your document?"))
			answer = dialog.run()
			dialog.destroy()
			runConfig = (answer == Gtk.ResponseType.YES)
			if runConfig:
				self._launch_AutoLaTeX('', [ '--createconfig=project', utils.DEFAULT_LOG_LEVEL ])
		if runConfig:
			config_window.open_configuration_dialog(self.window, True, directory)

    def on_delete_document_configuration_action_activate(self, action, data=None):
	directory = self._find_AutoLaTeX_dir()
	if directory:
		cfgFile = os.path.join(directory, '.autolatex_project.cfg')
		if os.path.exists(cfgFile):
			dialog = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, _T("Do you want to delete the document configuration?"))
			answer = dialog.run()
			dialog.destroy()
			if answer == Gtk.ResponseType.YES:
				os.unlink(cfgFile)
				self.do_update_state()

    def on_user_configuration_action_activate(self, action, data=None):
	directory = self._find_AutoLaTeX_dir()
	if directory:
		cfgFile = os.path.join(os.path.expanduser("~"),".autolatex")
		runConfig = True
		if not os.path.exists(cfgFile):
			dialog = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, _T("Do you want to create a configuration\nfile at the user level?"))
			answer = dialog.run()
			dialog.destroy()
			runConfig = (answer == Gtk.ResponseType.YES)
			if runConfig:
				self._launch_AutoLaTeX('', [ '--createconfig=user', utils.DEFAULT_LOG_LEVEL ])
		if runConfig:
				config_window.open_configuration_dialog(self.window, False, directory)

    def on_delete_user_configuration_action_activate(self, action, data=None):
	cfgFile = os.path.join(os.path.expanduser("~"), '.autolatex')
	if os.path.exists(cfgFile):
		dialog = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL, Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO, _T("Do you want to delete the user configuration?"))
		answer = dialog.run()
		dialog.destroy()
		if answer == Gtk.ResponseType.YES:
			os.unlink(cfgFile)
			self.do_update_state()

    def on_enable_synctex_action_activate(self, action, data=None):
	checkbox = self._general_actions.get_action('AutoLaTeXEnableSyncTeXAction')
	self._gsettings.set_force_synctex(checkbox.get_active())

    def on_update_for_synctex_action_activate(self, action, data=None):
	if self._is_TeX_document():
		directory = self._find_AutoLaTeX_dir()
		view = self.window.get_active_view()
		text_buffer = view.get_buffer()
		found = None
		# Search in the first tree lines
		if text_buffer.get_line_count() > 0:
			found = self.__search_for_synctex_flag(text_buffer, 0)
		# Search in the last tree lines
		if not found and text_buffer.get_line_count() > 3:
			found = self.__search_for_synctex_flag(text_buffer,
					max(3,text_buffer.get_line_count()-3))
		# Add the SyncTeX flag
		if not found:
			private_config = utils.backend_get_configuration(
						directory,
						'all', '__private__');
			main_file = private_config.get('input', 'latex file', '');
			current_dir = Gio.File.new_for_path(os.getcwd())
			main_file = current_dir.resolve_relative_path(main_file).get_path()
        		current_document = self.window.get_active_document()
			document_file = Gedit.Document.get_location(current_document)
			if document_file:
				document_filename = current_dir.resolve_relative_path(document_file.get_path())
				document_filename = document_filename.get_path()
				if main_file != document_filename:
					document_dir = document_file.get_parent()
					rel_path = os.path.relpath(main_file, document_dir.get_path())
					text_buffer.insert_interactive(
						text_buffer.get_iter_at_line(0),
						unicode("% mainfile: "+rel_path+"\n"),
						-1,
						view.get_editable())

    def __search_for_synctex_flag(self, text_buffer, line_number):
	found = None
	i = 0
	text_iter1 = text_buffer.get_iter_at_line(line_number)
	while text_iter1 and i<3 and not found:
		text_iter2 = text_iter1.copy();
		text_iter2.forward_to_line_end()
		line = text_iter1.get_visible_text(text_iter2)
		mo = re.match(self._syntex_regex, line)
		if mo:
			found = mo.group(1)
		text_iter1 = text_iter2
		if not text_iter1.forward_line():
			i = 4
		else:
			i = i + 1
	return found

    def on_gsettings_changed(self, settings, key, data=None):
	if key == 'force-synctex':
		checkbox = self._general_actions.get_action('AutoLaTeXEnableSyncTeXAction')
		checkbox.set_active(self._gsettings.get_force_synctex())

    def on_enable_synctex_action_activate(self, action, data=None):
	checkbox = self._general_actions.get_action('AutoLaTeXEnableSyncTeXAction')
	self._gsettings.set_force_synctex(checkbox.get_active())

    def on_makeflat_action_activate(self, action, data=None):
	self._launch_AutoLaTeX('makeflat', self._apply_general_autolatex_cli_options(
			[ '--noview' ]))

