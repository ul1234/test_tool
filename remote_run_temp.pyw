#############################################################################
#
#               TM500 Software
#               (C) Aeroflex Limited 2015
#               Longacres House
#               Six Hills Way
#               Stevenage SG1 2AN
#               Tel: +44 (0)1438 742200
#
#############################################################################
#
# FILE:         remote_run.pyw
# AUTHOR:       Tim Hoole (based on Steve Hill's cleacollab.pyw)
# Last Modified By :  Sanjeev Shukla
#           Changes :
#                    1. The COde has been modified to include the LTE Teamcity CLient for Binary Submission.
#                    2. Made More generc for use in Other RATs Also.
#
# DESCRIPTION:  This is a simple GUI application to join together Clearcase
#               (working on a private branch) and TeamCity Command Line Remote Run Tool
#
#############################################################################

import sys
import shutil
import re
import stat

try:
    print "\r",
    sys.stdout.flush()
except IOError:
    sys.stdout = file("remote_run.log", "w")
    sys.stderr = file("remote_run_error.log", "w")


try:
    import wx
except:
    # Doesn't look like wxPython is installed so use the built in GUI toolkit
    # to report the problem
    import Tkinter, tkMessageBox,tkFileDialog

    root = Tkinter.Tk()
    root.withdraw()
    tkMessageBox.showerror(
        "wxPython not installed",
        "This application needs v2.8 of wxPython.\n\nPlease install it from O:\\AAG_R&D_general\\Software\\MiscTools\\wxPython")
    sys.exit()

import os
from threading import Thread
sys.path.append(os.path.abspath(os.path.join('.', '.cache', 'utilities')))
from tcc import TeamCityRunner, TeamCityRunnerError
from add_batch_dialog import AddBatchDialog
sys.path.append(os.path.abspath(os.path.join('.', '..')))
import get_view_property
from simpleCheckTree import *
from clearcase import *
import get_options

#Read Variables from Get viewProperty

# Define the name that will be shown in the title bar
with file(os.path.join(os.getcwd(), ".cache\\latest.version")) as versionFile:
    _APP_VERSION = versionFile.readline()
_APP_NAME = "TeamCity Remote Run v" + _APP_VERSION

# Define the VCS mapping roots for each ToT
_LTE_CUE_VCS_MAP_ROOT = "=jetbrains.git://|\\\\stv-teamcitymas.aeroflex.corp\\git_projects\\cc_sync|\\"
_LTE_MUE_VCS_MAP_ROOT = "=jetbrains.git://|\\\\stv-teamcitymas.aeroflex.corp\\cc_views\\teamcitymaster_lte_mue_view|\\"
_LTE_SUE_VCS_MAP_ROOT = "=jetbrains.git://|\\\\stv-teamcitymas.aeroflex.corp\\cc_views\\teamcitymaster_lte_sue_view|\\"
_WCDMA_CUE_VCS_MAP_ROOT = "=jetbrains.git://|\\\\stv-teamcitymas.aeroflex.corp\\cc_views\\tc_wcdma_build_view|\\"
_BINARIES_VCS_MAP_ROOT = "=jetbrains.git://|\\\\stv-teamcitymas.aeroflex.corp\\git_projects\\remote_run|\\"

# This variable will be used to store any exception that occurs during explicitly protected
# sections of the script start-up (that is, prior the the wx App object being created and run)
# If this is not None when that happens, a message box will be shown and the application will
# once that is dismissed
startUpException = None

# Create the global Clearcase object that will be used to interact with ClearCase
try:
    cc = Clearcase(file("clearcase.log", "w"))
except IOError:
    print "Unable to create log-file!"
    cc = Clearcase()

# Time to create some more global variables/objects
# Make sure to capture any exceptions that might be raised
try:
    # Now ensure that all the VOBs that we need are mounted
    cc.mount(cc.configSpec.loadedVobs)

    # Make sure that we are in the root directory for this view
    os.chdir(cc.viewRoot)

    # Now create the object that will allow us to interface with TeamCity
    # Note that this checks that the command line tools are installed and accessible
    tcrun = TeamCityRunner()

except Exception, e:
    # Oops! Store the exception away to report later, when we are able
    startUpException = e


def single_instance():
    #Validate single instance of remote_run.pyw
    lockFile = 'tm_build_system\\teamcity\\remote_run.lock'
    try:
        if os.path.exists(lockFile):
            os.unlink(lockFile)
        os.open(lockFile, os.O_CREAT | os.O_EXCL | os.O_RDWR)
    except EnvironmentError:
        wx.MessageBox("An instance of remote_run.pyw is already running - aborting", 'ERROR', wx.OK | wx.ICON_ERROR)
        sys.exit()

def CreateIniEntryList(param,val):
    line = param + "="
    line = line + "["
    if len(val) > 0:
        line = line + "\""+val[0].replace('\\','\\\\')+"\""
        if len(val) > 1:
            for index in range (1,len(val)):
               line = line + ",\""+val[index].replace('\\','\\\\')+"\""
    line = line + "]\n"
    return line

def UpdateIniFile(param,val,list=False):
    fileName = "tm_build_system\\teamcity\\.cache\\utilities\\teamcity_ini.py"
    iniContents=[]
    if (list):
        line = CreateIniEntryList(param,val)
    else:
        line = param + "=\"" + val.replace('\\','\\\\') + "\"\n"
    if os.path.exists (fileName):
        try:
            readfrom = open (fileName,'r')
            iniContents = readfrom.readlines()
            readfrom.close()
        except:
            print "unable to open file for reading : ",fileName
    added = False
    for index in range (0,len(iniContents)):
        if iniContents[index].find(param) > -1:
            iniContents[index]=line
            added = True
    if not added:
        print 'adding the parameter ',param,'to Ini File'
        iniContents.append(line)
    try:
        writeto = open (fileName,'w+')
        writeto.writelines(iniContents)
        writeto.close()
    except:
        print 'Unable to Open File for writing.',fileName,'\n'

try:
    _automationFolder="lte_i_and_v\\automation\\"
    if (get_view_property.rat=='MRAT'):
        try:
            if (get_view_property.totAlias=='WCDMA'):
                _automationFolder="umts_i_and_v\\automation\\"
        except:
            print "totAlias does not exist"
    _batchFolder = os.path.join(_automationFolder,"Batch")
    _selectedBatchFiles = []
    _selectedBatchFolders = []
    _ftpFolderIni = os.path.join(cc.viewRoot,"tm_build_system\\build\\ftp")
    _tmaFolderIni = os.path.join(cc.viewRoot,"lte_win32_app\\TM500 Installation Software\\Files To Install\\Test Mobile Application")
    _selectedBuildType = 'MK3'
    _selectedStationConfig = ''
    _pydFolder = os.path.join(cc.viewRoot,"lte_shared_app\\database\\config_db\\cdd\\asn\\pyd")
    _batchFilter = ""
    _displayTMADialog='1'
    _displayPydDialog='1'
    _displayVectorDialog='1'
    _displayTestCaseDialog='1'
    sys.path.append('tm_build_system\\teamcity\\.cache\\utilities')
    import teamcity_ini
    try:
        _selectedBuildType = teamcity_ini._selectedBuildType
    except:
        UpdateIniFile("_selectedBuildType",_selectedBuildType)
    try:
        _selectedStationConfig = teamcity_ini._selectedStationConfig
    except:
        UpdateIniFile("_selectedStationConfig",_selectedStationConfig)
    try:
        _batchFolder = teamcity_ini._batchFolder
    except:
        UpdateIniFile("_batchFolder",_batchFolder)
    try:
        _selectedBatchFiles = teamcity_ini._selectedBatchFiles
    except:
        UpdateIniFile("_selectedBatchFiles",_selectedBatchFiles,True)
    try:
        _selectedBatchFolders = teamcity_ini._selectedBatchFolders
    except:
        UpdateIniFile("_selectedBatchFolders",_selectedBatchFolders,True)
    try:
        _ftpFolderIni = teamcity_ini._ftpFolderIni
    except:
        UpdateIniFile("_ftpFolderIni",_ftpFolderIni)
    try:
        _tmaFolderIni = teamcity_ini._tmaFolderIni
    except:
        UpdateIniFile("_tmaFolderIni",_tmaFolderIni)
    try:
        _pydFolder = teamcity_ini._pydFolder
    except:
        UpdateIniFile("_pydFolder",_pydFolder)
    try:
        _batchFilter = teamcity_ini._batchFilter
    except:
        UpdateIniFile("_batchFilter",_batchFilter)
    try:
        _displayTMADialog= teamcity_ini._displayTMADialog
    except:
        UpdateIniFile("_displayTMADialog",_displayTMADialog)
    try:
        _displayVectorDialog = teamcity_ini._displayVectorDialog
    except:
        UpdateIniFile("_displayVectorDialog",_displayVectorDialog)
    try:
        _displayTestCaseDialog = teamcity_ini._displayTestCaseDialog
    except:
        UpdateIniFile("_displayTestCaseDialog",_displayTestCaseDialog)
    try:
        _displayPydDialog = teamcity_ini._displayPydDialog
    except:
        UpdateIniFile("_displayPydDialog",_displayPydDialog)
except:
    print 'ini file does not exist : creating one '
    UpdateIniFile("_selectedBuildType",_selectedBuildType)
    UpdateIniFile("_selectedStationConfig",_selectedStationConfig)
    UpdateIniFile("_batchFolder",_batchFolder)
    UpdateIniFile("_selectedBatchFiles",_selectedBatchFiles,True)
    UpdateIniFile("_selectedBatchFolders",_selectedBatchFolders,True)
    UpdateIniFile("_ftpFolderIni",_ftpFolderIni)
    UpdateIniFile("_tmaFolderIni",_tmaFolderIni)
    UpdateIniFile("_pydFolder",_pydFolder)
    UpdateIniFile("_batchFilter",_batchFilter)
    UpdateIniFile("_displayTMADialog",_displayTMADialog)
    UpdateIniFile("_displayVectorDialog",_displayVectorDialog)
    UpdateIniFile("_displayTestCaseDialog",_displayTestCaseDialog)
    UpdateIniFile("_displayPydDialog",_displayPydDialog)

def on_rm_error( func, path, exc_info):
    # path contains the path of the file that couldn't be removed
    # let's just assume that it's read-only and unlink it.
    os.chmod( path, stat.S_IWRITE )
    os.unlink( path )

class DisplayDialog(wx.Dialog):
    """
    Dialog sub-class that displays the files that can be selected for the remote run
    and allows the user to select which ones should be used
    """
    def __init__(self, root, *args, **kwds):
        kwds["style"] = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX | wx.THICK_FRAME
        wx.Dialog.__init__(self, *args, **kwds)

        mainSizer = wx.BoxSizer(wx.VERTICAL)

        t = SimpleCheckTree(self, root)

        mainSizer = wx.BoxSizer(wx.VERTICAL)

        mainSizer.Add(t, 1, wx.EXPAND, 0)

        sz = wx.StdDialogButtonSizer()

        ok = wx.Button(self, wx.ID_OK)
        sz.AddButton(ok)

        cancel = wx.Button(self, wx.ID_CANCEL)
        sz.AddButton(cancel)

        sz.Realize()

        mainSizer.Add(sz, 0, wx.EXPAND | wx.ALL, 3)

        self.SetSizer(mainSizer)
        mainSizer.Fit(self)
        self.Layout()

        self.SetSize((400, 600))

class RemoteRunDialog(wx.Dialog):
    def get_teamcity_properties(self):
        self.vcsCheckEnabled = True
        try:
            self.__rat=get_view_property.rat
            self.__variant=get_view_property.variant
            self.__totAlias=""
            try:
                self.__totAlias=get_view_property.totAlias
                if (self.__totAlias.find('WCDMA') >= 0):
                    self.__rat='WCDMA'
                    self.__variant='EXTMUE'
            except:
                print "totAlias Does not exist"
        except:
            wx.MessageBox('ERROR OCCURED IN IMPORTING VIEW PROPERTIES.', 'ERROR', wx.OK | wx.ICON_INFORMATION)
            exit(1)
        self.__TeamCityServer = "https://emea-teamcity.aeroflex.corp"
        self.__binariesFolders=["tm_build_system\\build\\ftp"]
        self.__pydFolder="lte_shared_app\\database\\config_db\\cdd\\asn\\pyd"
        self.__configNameCheck = 'LTE'
        self.__pydFiles=["_tm500_asn1_codec_25.pyd","_tm500_asn1_codec_26.pyd",
                         "_tm500_asn1_codec_27.pyd"]
        self.__automationFolder="lte_i_and_v\\automation\\"
        self.__I_and_V_vob="lte_i_and_v"
        if (self.__totAlias=='WCDMA'):
            self.__binariesFolders.append("tm_build_system\\build\\legacy\\ftp")
            self.__configNameCheck = 'Wcdma_RavRun'
            self.__pydFolder="umts_shared_app\\database\\config_db\\cdd\\asn\\pyd"
            self.__automationFolder="umts_i_and_v\\automation\\"
            self.__I_and_V_vob="umts_i_and_v"
            self.__gitRepositoryName=_WCDMA_CUE_VCS_MAP_ROOT
        elif (self.__rat=='LTE'):
            if (self.__variant=='SUE'):
                self.__gitRepositoryName=_LTE_SUE_VCS_MAP_ROOT
            if (self.__variant=='MUE'):
                self.__gitRepositoryName=_LTE_MUE_VCS_MAP_ROOT
            if (self.__variant=='CUE'):
                self.__gitRepositoryName=_LTE_CUE_VCS_MAP_ROOT
        else:
            wx.MessageBox('This view is not supported\n'+self.__rat+':'+self.__variant+':'+self.__totAlias, 'ERROR', wx.OK | wx.ICON_INFORMATION)
            exit(1)
        self.supportedHWTypes=['MK1','MK3','MK4.x']
        self.__MK1_Builds=get_options.GetBuildOptions(self.__rat,self.__variant,'MK1')
        self.__MK3_Builds=get_options.GetBuildOptions(self.__rat,self.__variant,'MK3')
        self.__MK41_Builds=get_options.GetBuildOptions(self.__rat,self.__variant,'MK4.x')

    """
    Dialog sub-class for the top-level dialog. This is essentially a text box which pulls together
    various bits of information that may be useful in telling the user what is going on (and, occasionally)
    what has gone wrong!
    """
    def __init__(self, *args, **kwds):
        self.get_teamcity_properties()
        kwds["style"] = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX | wx.MINIMIZE_BOX | wx.THICK_FRAME
        wx.Dialog.__init__(self, *args, **kwds)
        self._textCtrl = wx.TextCtrl(self, -1, style = wx.TE_MULTILINE | wx.TE_READONLY)
        self._text = ""
        self._binariesRun = True
        self._manualFlag = False
        self._vectorUpdate = False
        self._expressRun = True
        self._umbraUpdate = False
        self._vectorDir=''
        self._mappingPropertiesFile = 'tm_build_system\\teamcity\\.cache\\.teamcity-mappings.properties'
        self._mappingProperties=[]
        self._mappingProperties.append('..\\..\\..\\' + self.__I_and_V_vob + self.__gitRepositoryName + self.__I_and_V_vob)
        self._mappingProperties.append('..\\..\\..\\tm_build_system' + self.__gitRepositoryName + 'tm_build_system')
        self._configParameters=[]
        self._MasterBatchFolderDir = 'tm_build_system\\teamcity\\.cache\\temp\\BatchFiles\\'
        if not os.path.exists('C:\\Temp'):
            try:
                os.mkdir('tm_build_system\\teamcity\\.cache\\temp')
            except:
                self._add_text('mkdir tm_build_system\\teamcity\\.cache\\temp failed')
        if os.path.exists('C:\\temp\\ftp'):
            try:
                os.system('attrib -R tm_build_system\\teamcity\\.cache\\temp\\ftp')
            except:
                self._add_text('rmdir /s/q tm_build_system\\teamcity\\.cache\\temp\\ftp failed')
        if False:
            if os.path.exists('tm_build_system\\teamcity\\.cache\\temp\\pyd'):
                try:
                    os.system('rmdir /s/q tm_build_system\\teamcity\\.cache\\temp\\pyd')
                except:
                    self._add_text('rmdir /s/q tm_build_system\\teamcity\\.cache\\temp\\pyd failed')
            if os.path.exists(self._MasterBatchFolderDir):
                try:
                    os.system('rmdir /s/q ' + self._MasterBatchFolderDir)
                except:
                    self._add_text('delete ' + self._MasterBatchFolderDir + 'failed')
        self.selectedStationConfig=''

        mainSizer = wx.BoxSizer(wx.VERTICAL)

        mainSizer.Add(self._textCtrl, 1, wx.EXPAND)

        self.Bind(wx.EVT_CLOSE, self.OnClose, self)

        self.SetSizer(mainSizer)
        mainSizer.Fit(self)
        self.Layout()

        self.SetSize((800, 300))
        self.SetTitle(_APP_NAME)

        self._add_text("Searching for files in Clearcase...")
        Thread(target = self._get_files_on_branch).start()

    def _add_mapping_property(self,binary,sourceDir,destinationDir):
        if binary:
            str = os.path.relpath(sourceDir.strip().rstrip('\\').rstrip('/'), os.path.dirname(self._mappingPropertiesFile)) + _BINARIES_VCS_MAP_ROOT + destinationDir.strip().rstrip('\\').rstrip('/')
        else:
            return
        str = str.rstrip('\\').replace(cc.viewRoot + '\\' + cc.viewRoot,cc.viewRoot)
        if not str in self._mappingProperties:
            self._mappingProperties.append(str)

    def _add_text(self, text, newline = True):
        self._text += text
        if newline:
            self._text += "\n"
        self._textCtrl.SetValue(self._text)
        self._textCtrl.SetInsertionPointEnd()

    def _add_exception(self, desc, e):
        indent = 4 * " "
        excText = indent + ("\n" + indent).join(str(e).splitlines())
        self._add_text("\n%s --> " % desc + e.__class__.__name__ + ":\n" + excText)

    def _copyDirectory(self,src, dest):
        try:
            self._add_text("************************")
            if os.path.exists(dest):
                self._add_text("Folder already exists : " + dest)
                self._add_text("Deleting folder :" + dest )
                self._add_text("------------------------")
                shutil.rmtree(dest)
            self._add_text("Copying the files from :" + src )
            self._add_text("                    to :" + dest )
            self._add_text("************************")
            shutil.copytree(src, dest)
        # Directories are the same
        except shutil.Error as e:
            self._add_text('Directory not copied. Error: %s' % e)
        # Any error saying that the directory doesn't exist
        except OSError as e:
            self._add_text('Directory not copied. Error: %s' % e)

    def _get_files_on_branch(self):
        wx.CallAfter(self._add_files_from_clearcase, []); return
        wx.CallAfter(self._add_text, "Getting branch...", newline = False)
        pb = cc.configSpec.privateBranch
        files = []
        self._branch = pb
        if self.vcsCheckEnabled:
            if pb is None:
                wx.CallAfter(self._add_text, "View is not on a private branch!\nCollecting checked-out files...")
                files = cc.find_checkouts(stripViewRoot = True, prefix = "")
            else:
                wx.CallAfter(self._add_text, "view is on branch '%s'" % pb)
                files = cc.find_elements_with_branch(pb, prefix = "")
                for st in files:
                    self._add_text(st)
        wx.CallAfter(self._add_files_from_clearcase, files)

    def _add_binaries_from_ftp_folder(self, ccFiles):
        self.buildType = 'None'
        self._ftplocation = 'External'
        _ftpAvailableflag = True
        for foldername in self.__binariesFolders:
            ftp_folder = foldername
            _ftpAvailableflag = _ftpAvailableflag and os.path.exists(ftp_folder)
        if os.path.exists('tm_build_system\\teamcity\\.cache\\temp\\ftp'):
            shutil.rmtree('tm_build_system\\teamcity\\.cache\\temp\\ftp', onerror = on_rm_error)
        if _ftpAvailableflag:
            dlg = wx.MessageDialog(None, 'FTP Folder detected in Current View', 'Do You want to Submit these Binaries.', wx.YES_NO | wx.ICON_QUESTION)
            result = dlg.ShowModal()
            if result == wx.ID_YES:
                for ftpRoot in self._ftpRoots:
                    self._add_text("::ftpRoot = %s" % ftpRoot)
                    self._add_mapping_property(True,cc.viewRoot + '\\'+ftpRoot,'ftp')
                    for dirName, subdirList, fileList in os.walk(ftpRoot):
                        # self._add_text("::dirName = %s" % dirName)
                        for file in fileList:
                            f = os.path.normpath(os.path.join(dirName, file))
                            self._add_text(":binary: file = %s" % f)
                            ccFiles.append(f)
                            self._ftplocation = 'Internal'
                    if (os.path.isfile('tm_build_system/tmp_files/history.log')):
                            self.buildType = self.get_buildtype('tm_build_system/tmp_files/history.log')
                            self._add_text(self.buildType)

    def _select_ftp_folder(self, ccFiles):
        self.buildType = 'None'
        dialog = wx.DirDialog(self, "Choose FTP directory.",style=wx.DD_DEFAULT_STYLE|wx.DD_DIR_MUST_EXIST )
        if (os.path.exists(_ftpFolderIni)):
            dialog.SetPath(_ftpFolderIni)
        else:
            dialog.SetPath(cc.viewRoot)
        if dialog.ShowModal() == wx.ID_OK:
            rel_loganalyse_path=["loganalyse","..\\..\\..\\loganalyse"]#relative to ftp folder
            rel_tools_path=["tools", "..\\..\\..\\tools"]#relative to ftp folder
            path = dialog.GetPath()
            _ftpFolder = path
            UpdateIniFile("_ftpFolderIni",_ftpFolder)
            destpath = os.path.normpath('tm_build_system\\teamcity\\.cache\\temp\\ftp')
            self._copyDirectory(path,destpath)
            #Check If Loganalyse directory has been added
            for loganalysePath in rel_loganalyse_path:
                checkpath = os.path.normpath(os.path.join(path,loganalysePath))
                if os.path.exists(checkpath):
                    self._copyDirectory(checkpath,os.path.normpath(os.path.join(destpath,"loganalyse")))
                    break
            #Check If tools directory has been added
            for toolsPath in rel_tools_path:
                checkpath = os.path.normpath(os.path.join(path,toolsPath))
                if os.path.exists(checkpath):
                    self._copyDirectory(checkpath,os.path.normpath(os.path.join(destpath,"tools")))
                    break
            p = path + "\\..\\..\\..\\build_all.txt"
            self._add_text(p)
            if (os.path.isfile(p)):
                self.buildType = self.get_buildtype(p)
                self._add_text(self.buildType)
            self._add_mapping_property(True,cc.viewRoot + '\\'+destpath,'ftp')
            for dirName, subdirList, fileList in os.walk(destpath):
                for file in fileList:
                    f = os.path.normpath(os.path.join(dirName, file))
                    self._add_text(":binary: file = %s" % f)
                    ccFiles.append(f)
        dialog.Destroy()

    def _select_TMA_folder(self, ccFiles):
        dialog = wx.DirDialog(self, "Choose TMA directory.",style=wx.DD_DEFAULT_STYLE|wx.DD_DIR_MUST_EXIST )
        if (os.path.exists(_tmaFolderIni)):
            dialog.SetPath(_tmaFolderIni)
        else:
            dialog.SetPath(cc.viewRoot)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            UpdateIniFile("_tmaFolderIni",path)
            destpath = os.path.normpath('tm_build_system\\teamcity\\.cache\\temp\\TMA')
            self._copyDirectory(path,destpath)
            self._add_mapping_property(True,cc.viewRoot + '\\'+destpath,'TMA')
            for dirName, subdirList, fileList in os.walk(destpath):
                for file in fileList:
                    f = os.path.normpath(os.path.join(dirName, file))
                    self._add_text(":binary: file = %s" % f)
                    ccFiles.append(f)
        dialog.Destroy()

    def _select_pyd_folder(self, ccFiles):
        #pyd files are required for NAS mode testing
        dialog = wx.DirDialog(self, "Choose pyd Source.",style=wx.DD_DEFAULT_STYLE )
        print cc.viewRoot+"\\"+self.__pydFolder
        if os.path.exists(_pydFolder):
            dialog.SetPath(_pydFolder)
        else:
            dialog.SetPath(os.path.join(cc.viewRoot,self.__pydFolder))
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            _pydFolderlocal = path
            UpdateIniFile("_pydFolder",_pydFolderlocal)
            destpath = os.path.normpath('tm_build_system\\teamcity\\.cache\\temp\\pyd')
            self._copyDirectory(path,destpath)
            _pydFiles = self.__pydFiles
            for dirName, subdirList, fileList in os.walk(destpath):
                for file in fileList:
                    if file in _pydFiles:
                        f = os.path.normpath(os.path.join(dirName, file))
                        self._add_text(":binary: file = %s" % f)
                        ccFiles.append(f)
            self._add_mapping_property(True,cc.viewRoot + '\\'+destpath,'ASN')
        dialog.Destroy()

    def AddToMasterBatch(self,ccFiles,batchFileName,option):
        batchFolderName = option
        if len(batchFolderName) == 0:
            batchFolderName = 'default'
        foldername = '???'
        try:
            foldername = 'tm_build_system\\teamcity\\.cache\\temp'
            if not os.path.exists(foldername):
                os.mkdir(foldername)
            foldername = self._MasterBatchFolderDir
            if not os.path.exists(foldername):
                os.mkdir(foldername)
            foldername = self._MasterBatchFolderDir+batchFolderName
            if not os.path.exists(foldername):
                os.mkdir(foldername)
        except:
            self._add_text('creation of folder'+foldername+' failed.')
        masterBatchName = os.path.join(os.path.join(self._MasterBatchFolderDir,batchFolderName),'RunBatchFiles.bat')
        masterBatchData=[]
        if not os.path.exists(masterBatchName):
            masterBatchData.append('cd %AUTO_TEST_HOME%\\Testing\\python\\\n')
            if (self._umbraUpdate):
                if (len(option.strip()) > 0):
                    masterBatchData.append("call python ttm_runner.py %firmwareUpdateBatch% -s %RAV_STATION_NAME%-" + option + '\n')
                else:
                    masterBatchData.append('call python ttm_runner.py %firmwareUpdateBatch%' + '\n')
        else:
            fo = open(masterBatchName)
            masterBatchData=fo.readlines()
            fo.close()
        if (len(option.strip()) > 0):
            masterBatchData.append('call python ttm_runner.py ' + batchFileName.strip() + ' -s %RAV_STATION_NAME%-' + option + '\n')
        else:
            masterBatchData.append('call python ttm_runner.py '+ batchFileName.strip() + '\n')
        try:
            fo = open(masterBatchName,'w')
            for line in masterBatchData:
                fo.write(line)
            fo.close()
        except:
            self._add_text('creation of file '+masterBatchName+' failed.')
        ccFiles.append(masterBatchName)
        self._add_mapping_property(True,cc.viewRoot +'\\' +self._MasterBatchFolderDir+batchFolderName,'BatchFiles\\'+batchFolderName)

    def GetBatchStationConfig(self,batchFileName,stationConfig=''):
        #set the default return Value
        stationConfigOption = stationConfig
        #get the list of options for the rat
        #d[0] is the list of display options
        #d[1] is the list of correcsponding options to be used in the ttm_runner Command.
        stationConfigList = [d for d in get_options.GetTestOptions(self.__rat,self.__variant)]
        if not get_options.DisplayTestOptions(self.__rat,self.__variant):
            for config in stationConfigList:
                if batchFileName.upper().find('_'+ config[0].upper() +'_') >-1:
                    stationConfigOption = config[1]
                    break
        return stationConfigOption

    def _select_TestCases(self, ccFiles):
        # ADDED  FOR RAV Engineers
        wildcard= "Test Case (*.txt)|*.txt"
        dialog = wx.FileDialog(None, "Choose a Test Case", os.getcwd(), "", wildcard, wx.OPEN|wx.FD_MULTIPLE)
        testcaselist = []
        while (dialog.ShowModal() == wx.ID_OK):
            tclist = dialog.GetPaths()
            for tc in tclist:
                testcaselist.append(tc)
        if len(testcaselist) > 0:
            if not (os.path.exists('tm_build_system\\teamcity\\.cache\\temp\\TestCases')):
                os.mkdir('tm_build_system\\teamcity\\.cache\\temp\\TestCases')
            for testcase in testcaselist:
                tcname = os.path.basename(testcase)
                self._add_text("Adding Test Case %s" % tcname)
                f = os.path.normpath(os.path.join('tm_build_system\\teamcity\\.cache\\temp\\TestCases\\', tcname))
                shutil.copy2(testcase,f)
                os.chmod( f, stat.S_IWRITE )
                ccFiles.append(f)
            self._add_mapping_property(True,cc.viewRoot + '\\' + 'tm_build_system\\teamcity\\.cache\\temp\\TestCases\\','TestCases')
        dialog.Destroy()

    def _select_Vector_folder(self, ccFiles):
        # ADDED  FOR RAV Engineers
        dialog = wx.DirDialog(self, "VECTORS : \n\nChoose Vector to be updated/copied on test station.\nCopy the vectors to this location.\nScheduler will copy these vectors to the test station.\nPlease make sure that the all test stations have access to this folder.",style=wx.DD_DEFAULT_STYLE|wx.DD_DIR_MUST_EXIST)
        if dialog.ShowModal() == wx.ID_OK:
            path = dialog.GetPath()
            self._vectorDir=path
            if os.path.isfile ('tm_build_system\\teamcity\\.cache\\teamcity.default.properties'):
                ccFiles.append('tm_build_system\\teamcity\\.cache\\teamcity.default.properties')
            vectors= [(f) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
            if not (os.path.isdir('tm_build_system\\teamcity\\.cache\\temp\\Vectors')):
                os.mkdir('tm_build_system\\teamcity\\.cache\\temp\\Vectors')
            vectorList=open(os.path.join('tm_build_system\\teamcity\\.cache\\temp\\Vectors','vectorList.txt'),'w')
            for vectorName in vectors:
                filename, file_extension = os.path.splitext(vectorName)
                if (file_extension.lower().find('aiq') > -1) or (file_extension.lower().find('dat') > -1):
                    vectorList.write(os.path.join(self._vectorDir,vectorName.strip())+'\n')
            vectorList.close()
            self._add_mapping_property(True,cc.viewRoot + '\\' + 'tm_build_system\\teamcity\\.cache\\temp\\Vectors','Vectors')
            f = os.path.normpath(os.path.join('tm_build_system\\teamcity\\.cache\\temp\\Vectors', 'vectorList.txt'))
            ccFiles.append(f)
        dialog.Destroy()

    def _add_pyd_files(self, ccFiles):
        if os.path.exists('tm_build_system\\teamcity\\.cache\\temp\\pyd'):
            shutil.rmtree('tm_build_system\\teamcity\\.cache\\temp\\pyd',onerror = on_rm_error)
        #Add alternate pyd folder since the FTP folder has changed.
        tempFtpPath = 'tm_build_system\\teamcity\\.cache\\temp\\FTP'
        if os.path.exists(tempFtpPath):
            self._select_pyd_folder(self.ccFiles)
        else:
            print tempFtpPath,"does Not Exist"
            _pydFiles = self.__pydFiles
            print self._pydPath
            for dirName, subdirList, fileList in os.walk(self._pydPath):
                for file in fileList:
                    if file in _pydFiles:
                        f = os.path.normpath(os.path.join(dirName, file))
                        self._add_text(":binary: file = %s" % f)
                        ccFiles.append(f)
                    self._add_mapping_property(True,cc.viewRoot + '\\'+self._pydPath,'ASN')

    def _add_batch_files(self, ccFiles):
        _addBatchDlg = AddBatchDialog(self, -1, 'Select Batch Files.',self.buildConfigDict)
        _addBatchDlg.SetBuildType(self.buildType)
        self._comment = "Remote run (binaries) "
        _addBatchDlg.SetComment(self._comment)
        _addBatchDlg._batchFolders = []
        for folder in _selectedBatchFolders:
            if os.path.exists(folder):
                if not (folder in _addBatchDlg._batchFolders):
                    _addBatchDlg._batchFolders.append(folder)
        if (len(_addBatchDlg._batchFolders) == 0):
            _addBatchDlg._batchFolders.append(self.__automationFolder +"batch\\")
        if not (len(_selectedBatchFiles) == len(_selectedBatchFolders)):
            _selectedBatchFilesLocal = []
            _selectedBatchFoldersLocal = []
            UpdateIniFile("_selectedBatchFiles",_selectedBatchFilesLocal,True)
            UpdateIniFile("_selectedBatchFolders",_selectedBatchFoldersLocal,True)
        for index in range(0,len(_selectedBatchFiles)):
            if os.path.exists(os.path.join(_selectedBatchFolders[index],_selectedBatchFiles[index])):
                _addBatchDlg.AddSelectedFile(_selectedBatchFiles[index],_selectedBatchFolders[index])
        _addBatchDlg.SetBuildType(_selectedBuildType)
        _addBatchDlg.SetStationConfig(_selectedStationConfig)
        _addBatchDlg.SetFilter(_batchFilter)
        _addBatchDlg.UpdateBatchFiles()
        _addBatchDlg.SetExpressFlag(self._expressRun)
        _addBatchDlg.ShowModal()
        tempBatchPath = os.path.normpath('tm_build_system\\teamcity\\.cache\\temp\\Batch')
        try:
            if os.path.exists(tempBatchPath):
                shutil.rmtree(tempBatchPath,onerror = on_rm_error)
        except:
            print 'unable to delete : ',tempBatchPath
        try:
            if not os.path.exists(tempBatchPath):
                os.makedirs(tempBatchPath)
        except:
            print 'unable to create : ',tempBatchPath
        if (len(_addBatchDlg.selectedBatchFilesList) > 0):
            self._comment = _addBatchDlg.GetComment()
            _selectedBatchFilesLocal = []
            _selectedBatchFoldersLocal = []
            self._manualFlag = _addBatchDlg.GetManualFlag()
            self._vectorUpdate = _addBatchDlg.GetVectorUpdateFlag()
            self._expressRun = _addBatchDlg.GetExpressFlag()
            self._umbraUpdate = _addBatchDlg.GetUmbraUpdateFlag()
            UpdateIniFile("_selectedBuildType",_addBatchDlg.GetBuildType())
            UpdateIniFile("_selectedStationConfig",_addBatchDlg.GetStationConfig())
            UpdateIniFile("_batchFilter",_addBatchDlg.GetFilter())
            self.selectedStationConfig=_addBatchDlg.GetStationConfig()
            for index in range(0,len(_addBatchDlg.selectedBatchFilesList)):
                f = os.path.normpath(os.path.join(_addBatchDlg.selectedFolders[index].strip(), _addBatchDlg.selectedBatchFilesList[index]))
                abspath = os.path.abspath(f)
                _selectedBatchFilesLocal.append(_addBatchDlg.selectedBatchFilesList[index])
                _selectedBatchFoldersLocal.append(os.path.abspath(_addBatchDlg.selectedFolders[index].strip()))
                if (abspath.find(cc.viewRoot) > -1):
                    if (_addBatchDlg.selectedFolders[index].find(cc.viewRoot) == 0):
                        self._add_mapping_property(True,_addBatchDlg.selectedFolders[index],'BatchFiles')
                    else:
                        self._add_mapping_property(True,cc.viewRoot + '\\'+_addBatchDlg.selectedFolders[index],'BatchFiles')
                    ccFiles.append(str(f.strip()))
                else:
                    #copy batch files to Temp folder
                    destFile = os.path.normpath(os.path.join(tempBatchPath, _addBatchDlg.selectedBatchFilesList[index]))
                    if not os.path.isfile(cc.viewRoot + destFile):
                        print "copying from :",f
                        print "          To :",tempBatchPath
                        shutil.copy(f, tempBatchPath)
                        ccFiles.append(destFile)
                        self._add_mapping_property(True,cc.viewRoot + '\\'+tempBatchPath,'BatchFiles')
                stationConfigOption=self.GetBatchStationConfig(_addBatchDlg.selectedBatchFilesList[index],self.selectedStationConfig)
                self.AddToMasterBatch(ccFiles,_addBatchDlg.selectedBatchFilesList[index],stationConfigOption)
            UpdateIniFile("_selectedBatchFiles",_selectedBatchFilesLocal,True)
            UpdateIniFile("_selectedBatchFolders",_selectedBatchFoldersLocal,True)
            self.buildType = _addBatchDlg.buildType
        else:
            sys.exit(0)

    def _add_TMA_files(self, ccFiles):
        if os.path.exists('tm_build_system\\teamcity\\.cache\\temp\\TMA'):
            shutil.rmtree('tm_build_system\\teamcity\\.cache\\temp\\TMA',onerror = on_rm_error)
        dlg = wx.MessageDialog(self,"Do you want to use TMA from View ?","", wx.YES_NO | wx.ICON_EXCLAMATION)
        addedFlag = False
        if os.path.exists('lte_win32_app\\TM500 Installation Software\\Files To Install\\Test Mobile Application'):
            if not (dlg.ShowModal() == wx.ID_NO):
                for dirName, subdirList, fileList in os.walk('lte_win32_app\\TM500 Installation Software\\Files To Install\\Test Mobile Application'):
                    for file in fileList:
                        f = os.path.normpath(os.path.join('\\' + dirName, file))
                        self._add_text(":binary: file = %s" % f)
                        ccFiles.append(f)
                    self._add_mapping_property(True,cc.viewRoot + '\\'+'lte_win32_app\\TM500 Installation Software\\Files To Install\\Test Mobile Application','TMA')
                    addedFlag = True
        if not addedFlag:
            #Add alternate TMA folder for testing.
            self._select_TMA_folder(self.ccFiles)

    def _add_file_for_manual_run(self, ccFiles):
        if os.path.isfile('tm_build_system\\teamcity\\.cache\\utilities\\SessionTimer.py'):
            ccFiles.append('tm_build_system\\teamcity\\.cache\\utilities\\SessionTimer.py')
            self._add_mapping_property(True,cc.viewRoot + '\\'+'tm_build_system\\teamcity\\.cache\\utilities\\','.')

    def _CreateConfigParametersFile(self, ccFiles):
        if (self._manualFlag):
            self._configParameters.append("env.ManualRun=True")
        if (self._vectorUpdate):
            self._configParameters.append("env.VectorUpdate=True")
        try:
            fo = open('tm_build_system\\teamcity\\.cache\\teamcity.default.properties','w')
            if (len (self._configParameters) > 0):
                for s in self._configParameters:
                    self._add_text(s)
                    fo.write(s+'\n')
                ccFiles.append('tm_build_system\\teamcity\\.cache\\teamcity.default.properties')
                self._add_mapping_property(True,cc.viewRoot + '\\'+'tm_build_system\\teamcity\\.cache','')
            fo.close()
        except:
            self._add_text( "Error creating the Config Parameters File.")

    def _add_files_from_clearcase(self, files):
        self._get_build_config_list()
        notVisiblePrompt = False
        notLoadedPrompt = False
        self.ccFiles = []
        self._pydPath = self.__pydFolder
        self._ftpRoots = self.__binariesFolders
        if os.path.exists('tm_build_system\\teamcity\\.cache\\Vectors\\NewVectorCopy.bat'):
            try:
               os.remove('tm_build_system\\teamcity\\.cache\\Vectors\\NewVectorCopy.bat')
            except OSError:
               pass
        if False:
            self._add_binaries_from_ftp_folder(self.ccFiles)
            if (self._ftplocation == 'External'):
                 #Add alternate FTP folder for testing.
                 self._select_ftp_folder(self.ccFiles)
            self._add_pyd_files(self.ccFiles)
            if (_displayTMADialog == "1"):
                self._add_TMA_files(self.ccFiles)
            #Add the user defined batch file and the list of batches to be tested during the remote Run.
            self._add_batch_files(self.ccFiles)
            #The Test Cases needs to be selected .
            if (_displayTestCaseDialog == "1"):
                self._select_TestCases(self.ccFiles)
            #The Vector folder needs to be selected for RAV team usage.
            if (_displayVectorDialog == "1"):
                self._select_Vector_folder(self.ccFiles)
            if (self._manualFlag):
                self._add_file_for_manual_run(self.ccFiles)
            self._CreateConfigParametersFile(self.ccFiles)
            
            if os.path.exists('tm_build_system\\teamcity\\clearcase.log'):
                self.ccFiles.append('tm_build_system\\teamcity\\clearcase.log')
            if os.path.exists('tm_build_system\\teamcity\\remote_run.log'):
                self.ccFiles.append('tm_build_system\\teamcity\\remote_run.log')
            if os.path.exists('tm_build_system\\teamcity\\remote_run_error.log'):
                self.ccFiles.append('tm_build_system\\teamcity\\remote_run_error.log')
            if self.vcsCheckEnabled:
                for f in files:
                    if ((self.__I_and_V_vob in f) or ('tm_build_system' in f)):
                        full = cc.viewRoot + '\\' + f
                        self._add_text(full)
                        if os.path.isdir(full):
                            # Ignore any directories
                            continue

                        if f.find("@@") >= 0:
                            # This element is not visible in the current view, probably due
                            # to it having been removed from the directory element
                            wx.CallAfter(self._add_text, "'%s' is not visible in view" % f)
                            if not notVisiblePrompt:
                                notVisiblePrompt = True
                                dlg = wx.MessageDialog(self,
                                        "There are files on the branch which are not visible in your view\n"
                                        "(probably because they were modifed but then deleted); do you want\n"
                                        "to continue but not include these files?",
                                        "Files not visible in view", wx.YES_NO | wx.ICON_EXCLAMATION)
                                if dlg.ShowModal() == wx.ID_NO:
                                    wx.CallAfter(self._add_text, "Aborted remote run")
                                    return
                            continue

                        if not os.path.exists(full):
                            # This element is not loaded in the current view, either due to
                            # a portion of the VOB heirarchy not being loaded or because an
                            # update is required
                            wx.CallAfter(self._add_text, "'%s' is not loaded in view" % f)
                            if not notLoadedPrompt:
                                notLoadedPrompt = True
                                dlg = wx.MessageDialog(self,
                                        "There are files on the branch which are not loaded in your view\n"
                                        "(you may not have them loaded via the load rules or you simply\n"
                                        "need to perform an update on some or all of your view); do you want\n"
                                        "to continue but not include these files?",
                                        "Files not loaded in view", wx.YES_NO | wx.ICON_EXCLAMATION)
                                if dlg.ShowModal() == wx.ID_NO:
                                    wx.CallAfter(self._add_text, "Aborted remote run")
                                    return
                            continue
                        self.ccFiles.append(f)
                    
        lines = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'upload_files.txt'), 'r').readlines()
        comments_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'comments.txt')
        self._comment = "Remote run (binaries) %s" % ('' if not os.path.isfile(comments_file) else '[%s]' % open(comments_file).read().strip())
        self.buildType = lines[0].strip()
        self.ccFiles = [line.strip() for line in lines[1:]]
        print 'buildType: %s, comment: %s, total %d files' % (self.buildType, self._comment, len(self.ccFiles))
        
        if len(self.ccFiles) == 0:
            self._add_text("No files found; aborting")
        else:
            self._add_text("Found %d files" % len(self.ccFiles))
            splitItems = {}
            for f in self.ccFiles:
                items = f.split(os.sep)
                if items[0] == "":
                    del items[0]
                name = items[-1]
                del items[-1]
                d = splitItems
                for item in items:
                    if item not in d.keys():
                        d[item] = {}
                    d = d[item]
                d[name] = f

            def collapse_dict(d):
                # self._add_text("collapse_dict...")
                for key, value in d.items():
                    if isinstance(value, dict):
                        collapse_dict(value)
                        if len(value) == 1:
                            del d[key]
                            k2, v2 = value.items()[0]
                            d[os.path.join(key, k2)] = v2
                return d

            collapse_dict(splitItems)
            Thread(target = self._populate_tree, args = (splitItems,)).start()

    def get_buildtype(self,filename):
        '''Gets build type from build type'''
        if (filename.lower().find("build_all") != -1):
            build_type_reg =  re.compile(r'\s*product\s*[=]\s*([0-9-a-z-A-Z_]+)\s*', re.I)
            try:
                config = open(filename, "r")
            except(IOError):
                self._add_text("-Cant find File: FAILED" + filename)
                return self._ProductType('None')
            for line in config.readlines():
                if line.lower().find("scons") != -1 and  line.lower().find("product") != -1:
                    regobj = build_type_reg.search(line)
                    if regobj:
                        return self._ProductType(regobj.group(1).upper().replace('\n','').replace('\s','').replace("'",'').replace('...',''))
        if (filename.lower().find("history") != -1):
            build_type_reg =  re.compile(r'\s*product\s*[=]\s*([0-9-a-z-A-Z_]+)\s*', re.I)
            try:
                config = open(filename, "r")
            except(IOError):
                self._add_text("-Cant find File: FAILED" + filename)
                return self._ProductType('None')
            type = 'None'
            for line in config.readlines():
                if line.lower().find("modifiers") != -1 and  line.lower().find("hde") == -1:
                    type = 'None'
                    if line.lower().find("product") != -1:
                        regobj = build_type_reg.search(line)
                        if regobj:
                            type = regobj.group(1).upper().replace('\n','').replace('\s','').replace("'",'').replace('...','')
            if (type != 'None'):
                return self._ProductType(type)
        return self._ProductType('SCONS_DEFAULT')

    def _ProductType(self,productId):
        if (productId.upper() in self.__MK1_Builds):
            return 'MK1'
        elif (productId.upper() in self.__MK3_Builds):
            return 'MK3'
        elif (productId.upper() in self.__MK41_Builds):
            return 'MK41'
        else:
            return 'MK3'

    def _populate_tree(self, splitItems):
        self._add_text("_populate_tree...")
        filesToAdd = []

        def dict_to_tree(d):
            items = []
            checkable = SimpleCheckItem.NO_CHECKBOX
            checkedoutPrompt = False
            hijackedPrompt = True
            includeHijacked = hijackedPrompt
            for key, value in sorted(d.items()):
                if isinstance(value, dict):
                    i, c = dict_to_tree(value)
                    f = SimpleCheckItem.FOLDED
                    if c != SimpleCheckItem.NO_CHECKBOX:
                        if key.find("ftp") >= 0:
                            c = SimpleCheckItem.UNCHECKED
                        else:
                            f = SimpleCheckItem.EXPANDED
                        checkable = SimpleCheckItem.CHECKED
                    items.append(SimpleCheckItem(key, i, checked = c, display = f))
                else:
                    if ((value.lower().find("tm_build_system\\build") >= 0) or (value.lower().find("tm_build_system\\teamcity\\.cache\\temp") >= 0)):
                        cv = value + '//BUILD_ARTIFACT'
                    else:
                        try:
                            if (value.find(cc.viewRoot ) == 0):
                                filenameCC = value
                            else:
                                filenameCC = cc.viewRoot + '\\' + value
                            cv = cc.get_element_version(filenameCC)
                        except ClearCaseHijackedError:
                            # This element is hijacked
                            wx.CallAfter(self._add_text, "'%s' is view private or hijacked" % value)

                            if not hijackedPrompt:
                                hijackedPrompt = True
                                dlg = wx.MessageDialog(self,
                                        "There are files on the branch which are hijacked;"
                                        "do you want to include these files?",
                                        "Files hijacked in view", wx.YES_NO | wx.ICON_EXCLAMATION)
                                if dlg.ShowModal() == wx.ID_YES:
                                    includeHijacked = True

                            if includeHijacked:
                                i1 = SimpleCheckItem(("RED", "Hijacked File: " + value), checked = SimpleCheckItem.NO_CHECKBOX)
                                i = SimpleCheckItem(key, [i1], checked = SimpleCheckItem.CHECKED, display = SimpleCheckItem.FOLDED)
                                items.append(i)
                                filesToAdd.append((i, value, value + '//BLAH'))
                                checkable = SimpleCheckItem.CHECKED

                            continue

                        if cv.find("CHECKEDOUT") >= 0:
                            # This element is checked out
                            wx.CallAfter(self._add_text, "'%s' is checked out" % value)
                            if not checkedoutPrompt:
                                checkedoutPrompt = True
                                dlg = wx.MessageDialog(self,
                                        "This file is currently checked out;"
                                        "do you want to include this files?",
                                        "Files checked out in view", wx.YES_NO | wx.ICON_EXCLAMATION)
                                if True or dlg.ShowModal() == wx.ID_YES:
                                    i1 = SimpleCheckItem(("ORANGE", "Checked out File: " + cv), checked = SimpleCheckItem.NO_CHECKBOX)
                                    i = SimpleCheckItem(key, [i1], checked = SimpleCheckItem.CHECKED, display = SimpleCheckItem.FOLDED)
                                    items.append(i)
                                    filesToAdd.append((i, value, cv))
                                    checkable = SimpleCheckItem.CHECKED
                                    continue
                                else:
                                    continue

                    i1 = SimpleCheckItem(("GREY", "New File: version " + cv), checked = SimpleCheckItem.NO_CHECKBOX)
                    i = SimpleCheckItem(key, [i1], checked = SimpleCheckItem.CHECKED, display = SimpleCheckItem.FOLDED)
                    items.append(i)
                    filesToAdd.append((i, value, cv))
                    checkable = SimpleCheckItem.CHECKED

            return items, checkable

        try:
            items, checkable = dict_to_tree(splitItems)
        except Exception, e:
            wx.CallAfter(self._add_exception, "Failed to populate tree", e)
            return

        wx.CallAfter(self._create_sub_dialog, items, checkable, filesToAdd)

    def _create_sub_dialog(self, items, checkable, filesToAdd):
        root = SimpleCheckItem(cc.viewRoot, items, checked = checkable, display = SimpleCheckItem.EXPANDED if checkable != SimpleCheckItem.NO_CHECKBOX else SimpleCheckItem.FOLDED)
        root.flow_up()

        title = "Select files to include in the remote run..."

        dlg = DisplayDialog(root, None, -1 , title)
        if dlg.ShowModal() == wx.ID_OK:
            dlg.Destroy()
            filesToAdd = [(f[1], f[2]) for f in filesToAdd if f[0].get_check_state() == SimpleCheckItem.CHECKED]
            if len(filesToAdd) > 0:
                self._add_text("Getting versions of new files on branch...")
                Thread(target = self._create_remote_run, args = (filesToAdd,)).start()
            else:
                self._add_text("No files selected; aborting")
        else:
            dlg.Destroy()
            self.Destroy()

    def _get_build_config_list(self):
        self.buildConfigDict = {}
        builds = tcrun.get_remote_builds()
        projects = []
        items = []
        buildItems = []
        for hwtype in self.supportedHWTypes:
            configlist = [d for d in get_options.GetTestOptions(self.__rat,self.__variant)]
            for b in builds:
                if b[:3] == 'id ':
                    pos_project = b.index('project')
                    pos_name = b.index('name')
                    pos_status = b.index('status')
                    pos_description = b.index('description')
                else:
                    _id = b[:pos_project - 1].rstrip()
                    if not (hwtype in self.buildConfigDict.keys()):
                        self.buildConfigDict[hwtype] = {}
                    for config in configlist:
                        if config[0]=='':
                            configchkstring = '_'+hwtype.upper()+ '_DEFAULT_'
                        else:
                            configchkstring = '_'+hwtype.upper()+ '_'+config[0].strip().upper()+ '_'
                        if (self.IsConfigValid(_id,hwtype,config[0])):
                            if not (config[1] in self.buildConfigDict[hwtype].keys()):
                                self.buildConfigDict[hwtype][config[1]] = (_id,b[pos_name:pos_status - 1].rstrip())
                                #print hwtype,config[1],_id

    def IsConfigValid(self,configId,hwType,stationConfig):
        valid = False
        hwType = hwType.replace(".","_",100).upper()
        if (configId.upper().find(self.__rat.upper().strip()) >= 0):
            if (configId.upper().find(self.__variant.upper().strip()) >= 0):
                if (configId.upper().find(hwType) >= 0):
                    if (configId.upper().find(stationConfig.upper()) >= 0):
                        valid = True
        return valid

    def _create_remote_run(self, filesToAdd):
        try:
            # filesToAdd = [(f[0], cc.get_element_version(cc.viewRoot + f[0])) if f[1] is None else f for f in filesToAdd]
            filesToAdd = [(f[0]) if f[1] is None else f for f in filesToAdd]
        except Exception, e:
            wx.CallAfter(self._add_exception, "Failed to get versions", e)
            return

        builds = tcrun.get_remote_builds()
        projects = []
        items = []
        buildItems = []
        for b in builds:
            if True:
                if b[:3] == 'id ':
                    pos_project = b.index('project')
                    pos_name = b.index('name')
                    pos_status = b.index('status')
                    pos_description = b.index('description')
                else:
                    _id = b[:pos_project - 1].rstrip()
                    configNameCheck=False
                    configNames = [d for d in os.listdir(self._MasterBatchFolderDir) if not os.path.isfile(os.path.join(self._MasterBatchFolderDir, d))]
                    for configName in configNames:
                        #check if the build belong to right config on the build and station config
                        if (self.IsConfigValid(_id,self.buildType,configName)):
                            configNameCheck=True
                            break
                        else:
                            self._add_text( 'skipped :' + _id.upper()+':'+ self.buildType + ':' +configName.replace(".","_",100))
                    if not configNameCheck:
                        #eliminate the build based on the build and station config
                        continue
                    _proj = b[pos_project:pos_name - 1].rstrip()
                    _name = b[pos_name:pos_status - 1].rstrip()
                    _status = b[pos_status:pos_description - 1].rstrip()
                    _description = b[pos_description:].rstrip()
                    _notDebugAdmin = not (os.path.isfile("c:\\debugAdmin.txt"))
                    _notBinariesName = False
                    _notBinariesName = (_id.upper().find('_BINARIES') == -1)
                    rat = (_id.upper().find(self.__rat.upper() + '_') != -1)
                    _dailyRavRun = _proj.lower().find('daily') != -1
                    if _notDebugAdmin:
                        if _name[0] == '*': continue
                        if _notBinariesName: continue
                    if _dailyRavRun: continue
                    #
                    projExists = False
                    # now find associated project
                    for p in projects:
                        if p[0][0] == _proj:
                            p.append(([_proj, _name, _id, _description]))
                            projExists = True

                    if not projExists:
                        projects.append(([[_proj, _name, _id, _description]]))
                    # create a new project item

            else:
                b = str.split(b)[0]
                if b != "id":
                    i = SimpleCheckItem(b)
                    items.append(i)
                    buildItems.append((i, b))

        self._add_text("%d projects\n" % len(projects))
        for p in projects:
            builds = []
            self._add_text("project %s" % p[0])
            self._add_text("%d builds" % len(p))
            for x in p:
                self._add_text("   %s" % x)
                i = SimpleCheckItem(x[1])
                builds.append(i)
                buildItems.append((i, x[2]))

            i = SimpleCheckItem(p[0][0], builds)
            items.append(i)
        wx.CallAfter(self._select_builds_dialog, items, SimpleCheckItem.CHECKED, filesToAdd, buildItems)

    def _select_builds_dialog(self, items, checkable, filesToAdd, builds):
        try:
            fo = open(self._mappingPropertiesFile,'w')
            for s in self._mappingProperties:
                self._add_text( s)
                fo.write(s+'\n')
            fo.close()
        except:
            self._add_text( "Error creating the Properties File.")
        root = SimpleCheckItem("TeamCity", items, checked = checkable, display = SimpleCheckItem.EXPANDED if checkable != SimpleCheckItem.NO_CHECKBOX else SimpleCheckItem.FOLDED)
        root.flow_up()
        title = "Select builds/tests to run..."
        dlg = DisplayDialog(root, None, -1 , title)
        if dlg.ShowModal() == wx.ID_OK:
            dlg.Destroy()
            builds = [(f[1]) for f in builds if f[0].get_check_state() == SimpleCheckItem.CHECKED]
            if len(builds) > 0:
                self._add_text("Getting versions of new files on branch...")
                Thread(target = self._trigger_remote_run, args = (filesToAdd, builds)).start()
            else:
                self._add_text("No builds/tests selected; aborting")
        else:
            dlg.Destroy()
            self.Destroy()

    def _trigger_remote_run(self, filesToAdd, builds):
        wx.CallAfter(self._add_text, "Triggering remote run with %d files..." % len(filesToAdd))
        if cc.configSpec.privateBranch:
            comment =  self._comment + "< "+cc.configSpec.privateBranch+" >"
        else:
            comment = self._comment + "< integration branch >"
        try:
            tcrun.add_clearcase_versions(None, comment, filesToAdd, builds, stdoutCallback = self._output_tcc9_output)
            wx.CallAfter(self._add_text, "Done")
        except TeamCityRunnerError, e:
            wx.CallAfter(self._add_text, "TeamCityRunner error: " + str(e))

    def _output_tcc9_output(self, text):
        wx.CallAfter(self._add_text, text, newline = False)

    def OnClose(self, e):
        self.Destroy()

class RemoteRunApp(wx.App):
    """
    Define a minimal application to run the top-level dialog
    """
    def OnInit(self):
        try:
            wx.InitAllImageHandlers()
            single_instance()
            if startUpException is not None:
                wx.MessageBox(str(startUpException), startUpException.__class__.__name__)
                raise startUpException
            try:
                if not tcrun.check_logged_in():
                    dlg = LoginDialog()
                    dlg.ShowModal()
                    if not dlg.logged_in:
                        raise Exception("TeamCity Login failed")
                else:
                    print "logged in."

                dialog = RemoteRunDialog(None, -1, "")
            except Exception, e:
                wx.MessageBox(str(e), e.__class__.__name__)
                raise

            self.SetTopWindow(dialog)
            dialog.Show()
        except:
            print "Error occured in Init. Remote App."
            raise
        return 1

class LoginDialog(wx.Dialog):
    """
    Class to define login dialog
    """
    def __init__(self):
        """Constructor"""
        self.__TeamCityServer = "https://emea-teamcity.aeroflex.corp"
        wx.Dialog.__init__(self, None, title = "TeamCity Login")
        self.logged_in = False
        self.failCnt = 0

        # user info
        user_sizer = wx.BoxSizer(wx.HORIZONTAL)
        user_lbl = wx.StaticText(self, label = "Username:")
        user_sizer.Add(user_lbl, 0, wx.ALL | wx.CENTER, 5)
        self.user = wx.TextCtrl(self)
        user_sizer.Add(self.user, 0, wx.ALL, 5)

        # pass info
        p_sizer = wx.BoxSizer(wx.HORIZONTAL)
        p_lbl = wx.StaticText(self, label = "Password:")
        p_sizer.Add(p_lbl, 0, wx.ALL | wx.CENTER, 5)
        self.password = wx.TextCtrl(self, style = wx.TE_PASSWORD | wx.TE_PROCESS_ENTER)
        self.password.Bind(wx.EVT_TEXT_ENTER, self.onLogin)
        p_sizer.Add(self.password, 0, wx.ALL, 5)

        server_link = wx.HyperlinkCtrl(self, id = 8, label = "TeamCity Server", url = self.__TeamCityServer)

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(server_link, 0, wx.ALL | wx.CENTER, 5)
        main_sizer.Add(user_sizer, 0, wx.ALL, 5)
        main_sizer.Add(p_sizer, 0, wx.ALL, 5)

        btn = wx.Button(self, label = "Login")
        btn.Bind(wx.EVT_BUTTON, self.onLogin)
        main_sizer.Add(btn, 0, wx.ALL | wx.CENTER, 5)

        self.status_lbl = wx.TextCtrl(self, value = "Please use your ClearCase username   e.g. thoole", size = wx.Size(300, 20), style = wx.TE_READONLY | wx.TE_RICH)
        self.status_lbl.SetBackgroundColour(wx.LIGHT_GREY)
        main_sizer.Add(self.status_lbl, 0, wx.ALL | wx.CENTER, 5)

        self.SetSizer(main_sizer)

    def onLogin(self, event):
        """
        Check credentials and login
        """
        if tcrun.login(self.user.GetValue(), self.password.GetValue()):
            self.logged_in = True
            self.Close()
        else:
            self.failCnt += 1
            self.status_lbl.SetValue("Login failed  [%d]" % self.failCnt)
            print "Username or password is incorrect!"


if __name__ == "__main__":
    # We've been run as a top-level script so create and run the application
    remoteRun = RemoteRunApp(0)
    remoteRun.MainLoop()
# (C) Aeroflex Limited 2015

