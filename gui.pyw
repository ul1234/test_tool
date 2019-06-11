#!/usr/bin/python
# -*- coding: utf-8 -*-

import wx
import win32api, sys, os, ConfigParser
from run_cmd import RunCmd

CMD = RunCmd()
#CMD.DEBUG = True

class IniConfig(object):
    def __init__(self, ini_file):
        self.ini = ConfigParser.RawConfigParser()
        self.ini_file = ini_file
        if not os.path.isfile(ini_file): open(ini_file, 'w').close()
        self.ini.read(ini_file)

    def write_back(self):
        with open(self.ini_file, 'w+') as f_write:
            self.ini.write(f_write)

    def option_name(self, option):
        return option.replace(' ', '_').replace(':', '')

    def write(self, box_name, option, value):
        option = self.option_name(option)
        try:
            self.ini.set(box_name, option, value)
        except ConfigParser.NoSectionError:
            self.ini.add_section(box_name)
            self.ini.set(box_name, option, value)
        self.write_back()

    def read(self, box_name, option):
        option = self.option_name(option)
        value = ''
        try:
            value = self.ini.get(box_name, option)
        except ConfigParser.NoSectionError:
            self.ini.add_section(box_name)
        except ConfigParser.NoOptionError:
            pass
        return value

INI = IniConfig('config.ini')


class Box(wx.StaticBox):
    def __init__(self, parent):
        self.name = self.__class__.__name__[3:]
        super(Box, self).__init__(parent, wx.ID_ANY, self.name)
        self.box_sizer = wx.StaticBoxSizer(self, wx.VERTICAL)
        self.ini_sync = []
        self.init()
        self.ini_sync_update_read()

    def ini_sync_update_read(self):
        for name, option, control in self.ini_sync:
            value = INI.read(name, option)
            if not value and isinstance(control, wx.ComboBox):
                control.SetSelection(0)
            else:
                control.SetValue(value)

    def ini_sync_update_write(self):
        for name, option, control in self.ini_sync:
            INI.write(name, option, control.GetValue())

    def add_line(self, controls):
        h_sizer = wx.BoxSizer(wx.HORIZONTAL)
        for c in controls:
            if isinstance(c, str): c = wx.StaticText(self, -1, c)
            h_sizer.Add(c, 0, wx.ALL, 5)
        self.box_sizer.Add(h_sizer)

    def add_select_folder_line(self, folder_text):
        self.text_select_folder = wx.TextCtrl(self, -1, size = (300, -1), style = wx.ALIGN_LEFT)
        self.ini_sync.append((self.name, folder_text, self.text_select_folder))

        button_select = wx.Button(self, -1, "Select ...")
        button_select.Bind(wx.EVT_BUTTON, self.select_folder(folder_text, self.text_select_folder))

        self.add_line([folder_text, self.text_select_folder, button_select])

        def get_folder():
            folder = self.text_select_folder.GetValue()
            if folder.find(' ') >= 0: folder = '"{}"'.format(folder)
            return folder
        return get_folder

    def add_select_files_line(self, files_text, get_folder, files_callback = None):
        button = wx.Button(self, -1, files_text)
        button.Bind(wx.EVT_BUTTON, self.select_files(get_folder, files_callback))

        self.add_line([button])

    def select_folder(self, folder_text, edit_project_path):
        def on_select_folder(event):
            dlg = wx.DirDialog(self, "Choose Folder:", defaultPath = edit_project_path.GetValue(), style = wx.DD_DEFAULT_STYLE|wx.DD_DIR_MUST_EXIST)
            if dlg.ShowModal() == wx.ID_OK:
                edit_project_path.Clear()
                edit_project_path.SetValue(dlg.GetPath())
            dlg.Destroy()
        return on_select_folder

    def select_files(self, get_folder, files_callback = None):
        def on_select_files(event):
            self.ini_sync_update_write()
            dlg = wx.FileDialog(self, "Choose Files:", defaultDir = get_folder(), style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST | wx.FD_MULTIPLE)
            files = []
            if (dlg.ShowModal() == wx.ID_OK):
                files = [os.path.basename(f) for f in dlg.Paths]
                files = ['"{}"'.format(f) if f.find(' ') >= 0 else f for f in files]
                files = ' '.join(files)
                if files and files_callback: files_callback(os.path.dirname(dlg.Paths[0]), files)
            return files
        return on_select_files

class Tab(wx.Panel):
    def __init__(self, parent):
        super(Tab, self).__init__(parent)

        self.name = self.__class__.__name__[3:]
        v_sizer = wx.BoxSizer(wx.VERTICAL)
        for Box in self.boxes():
            box = Box(self)
            v_sizer.Add(box.box_sizer, 0, wx.ALL|wx.EXPAND, 10)
        self.SetSizer(v_sizer)


class BoxPresub(Box):
    def init(self):
        self.choice_letters = wx.ComboBox(self, choices = self.driver_letters(), style = wx.CB_READONLY)
        self.ini_sync.append((self.name, "Driver Letter", self.choice_letters))

        self.add_line(["Dynamic View:", self.choice_letters])

        self.get_project_path = self.add_select_folder_line("Project Path:")

        button = wx.Button(self, -1, "Run Presub")
        button.Bind(wx.EVT_BUTTON, self.run)

        self.add_line([button])

    def driver_letters(self):
        drives = win32api.GetLogicalDriveStrings()
        return [s[:2] for s in drives.split('\000')[-2::-1]]

    def run(self, event):
        self.ini_sync_update_write()
        dynamic_view = self.choice_letters.GetValue()
        CMD.run('presub {} -v {}'.format(self.get_project_path(), dynamic_view))

class BoxSmokeTest(Box):
    def init(self):
        self.choice_batch = wx.ComboBox(self, choices = ['All', '1Cell', '2Cell'], style = wx.CB_READONLY)
        self.choice_batch.SetSelection(0)

        self.add_line(["Smoke Test Batch:", self.choice_batch])

        self.get_project_path = self.add_select_folder_line("Project Path:")

        button = wx.Button(self, -1, "Run Smoke Test")
        button.Bind(wx.EVT_BUTTON, self.run)

        self.add_line([button])

    def run(self, event):
        batch = self.choice_batch.GetValue()
        batch_str = '' if batch == 'All' else '-b {}'.format(batch)
        CMD.run('sanity {} {} '.format(batch_str, self.get_project_path()))

class BoxGenerateLog(Box):
    def init(self):
        self.get_log_folder = self.add_select_folder_line("Log Folder:")

        self.add_select_files_line("Generate Logs ...", self.get_log_folder, self.generate_log)

    def generate_log(self, folder, files):
        CMD.run('glog -0 -p {} {}'.format(folder, files))

class BoxSplitLog(Box):
    def init(self):
        self.get_log_folder = self.add_select_folder_line("Log Folder:")

        self.choice_size = wx.ComboBox(self, choices = ['30', '80', '150'])
        self.choice_size.SetSelection(0)

        self.choice_pieces = wx.ComboBox(self, choices = ['3 pieces - First Intermidate Last', 'All pieces', 'Only last piece'])
        self.choice_pieces.SetSelection(0)

        self.add_line(["Each Piece Size (MBytes)", self.choice_size, "Split Pieces", self.choice_pieces])

        self.add_select_files_line("Split Logs ...", self.get_log_folder, self.split_files)

    def split_files(self, folder, files):
        piece_size = self.choice_size.GetValue()
        pieces_option = self.choice_pieces.GetSelection()
        pieces_value = self.choice_pieces.GetValue()  # -1 means self-defined
        pieces_str_list = ['-i {}'.format(pieces_value), '', '-a', '-l 1']
        pieces_str = pieces_str_list[pieces_option + 1]

        CMD.run('spl -p {} -s {} {} {}'.format(folder, piece_size, pieces_str, files))

class BoxSearchLog(Box):
    def init(self):
        self.get_log_folder = self.add_select_folder_line("Log Folder:")

        self.choice_size = wx.ComboBox(self, choices = ['30', '80', '150'])
        self.choice_size.SetSelection(0)

        self.add_line(["Each Piece Size (MBytes)", self.choice_size])

        self.text_search_pattern = wx.ComboBox(self, choices = ['DLC_PDCCH_CTRL_CNFG', 'DLC_PDCCH_BRP_MSG_TO'])
        self.ini_sync.append((self.name, "Search Pattern", self.text_search_pattern))

        self.add_line(["Search Pattern (Regular EXP)", self.text_search_pattern])

        self.add_select_files_line("Search Logs ...", self.get_log_folder, self.search_logs)

    def search_logs(self, folder, files):
        piece_size = self.choice_size.GetValue()
        search_pattern = self.text_search_pattern.GetValue()
        if search_pattern.strip():
            CMD.run('search -p {} -s {} -r {} {}'.format(folder, piece_size, search_pattern, files))
        else:
            print('Error: Search Pattern is empty!')

class BoxFilterLog(Box):
    def init(self):
        self.get_log_folder = self.add_select_folder_line("Log Folder:")

        self.text_search_pattern = wx.ComboBox(self, choices = ['DLC_PDCCH_CTRL_CNFG', 'DLC_PDCCH_BRP_MSG_TO'])
        self.ini_sync.append((self.name, "Search Pattern", self.text_search_pattern))

        self.add_line(["Search Pattern (Regular EXP)", self.text_search_pattern])

        self.add_select_files_line("Filter Logs ...", self.get_log_folder, self.filter_logs)

    def filter_logs(self, folder, files):
        search_pattern = self.text_search_pattern.GetValue()
        if search_pattern.strip():
            CMD.run('filter -p {} -r {} {}'.format(folder, search_pattern, files))
        else:
            print('Error: Search Pattern is empty!')

class TabTeamcity(Tab):
    def boxes(self):
        return [BoxPresub, BoxSmokeTest]

class TabLog(Tab):
    def boxes(self):
        return [BoxGenerateLog, BoxSplitLog, BoxSearchLog, BoxFilterLog]

class TabAnalyse(Tab):
    def boxes(self):
        return []

class TabHdeScript(Tab):
    def boxes(self):
        return []

ALL_TABS = [TabTeamcity, TabLog, TabAnalyse, TabHdeScript]

class RedirectPrint(object):
    def __init__(self, text_log):
        self.text_log = text_log

    def write(self, s):
        self.text_log.WriteText(s)
        #wx.CallAfter(self.text_log.WriteText, s)

    def flush(self):
        pass

class MainFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, title = "Test tool", size = (1200,700))

        panel = wx.Panel(self, style = wx.RAISED_BORDER)

        notebook = wx.Notebook(panel)

        for Tab in ALL_TABS:
            tab = Tab(notebook)
            notebook.AddPage(tab, tab.name)

        self.text_log = wx.TextCtrl(panel, wx.ID_ANY, style = wx.TE_MULTILINE|wx.TE_READONLY|wx.HSCROLL|wx.TE_DONTWRAP)
        #self.text_log.ShowPosition(self.text_log.GetLastPosition())  # scroll to bottom
        sys.stdout = RedirectPrint(self.text_log)       # redirect stdout

        h_sizer = wx.BoxSizer(wx.HORIZONTAL)
        h_sizer.Add(notebook, 0, wx.EXPAND|wx.ALL, 10)
        h_sizer.Add(self.text_log, 1, wx.EXPAND|wx.ALL, 10)
        panel.SetSizer(h_sizer)

        self.Centre()


if __name__ == "__main__":
    app = wx.App()
    MainFrame().Show()
    app.MainLoop()

