#!/usr/bin/env python
# coding: utf-8


import sys
import os
import signal
signal.signal(signal.SIGINT, signal.SIG_DFL)

import json
import time
import copy
import datetime
from fabric import *
from collections import OrderedDict as ODict
import threading


from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtWidgets import QWidget, QSplitter, QVBoxLayout, QHBoxLayout
from PyQt5.QtWidgets import QDialog, QFileDialog, QFileSystemModel, qApp
from PyQt5.QtWidgets import QStyle, QListView, QTreeView, QMessageBox
from PyQt5.QtWidgets import QLineEdit, QPushButton as QButton, QAction
from PyQt5.QtWidgets import QAbstractItemView, QGridLayout, QMessageBox
from PyQt5.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem
from PyQt5.QtMultimedia import QMediaPlayer, QMediaPlaylist, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtCore import Qt, QDir, QUrl, QTimer
from PyQt5.QtGui import QFont


abs_path = os.path.abspath(__file__)
g_conf_file = os.path.join(os.path.dirname(abs_path), 'utran.conf')


class Config(dict):
    def loadCfg(self):
        print('load config')
        try:
            if os.path.exists(g_conf_file):
                self.update(json.load(open(g_conf_file, 'r')))
            else:
                with open(g_conf_file, 'w+') as conf:
                    json.dump(self, conf)
                    write(conf, json.dumps({}))
        except Exception as e:
            print(e)
            self._conf = None

    def saveCfg(self):
        json.dump(self, open(g_conf_file, 'w'))

g_conf = Config()
g_conf.loadCfg()


class LocalDirTree(QTreeView):
    def __init__(self):
        super().__init__()
        self._filePath = None
        if 'localdir' in g_conf:
            self.updateDir(g_conf['localdir'])
        else:
            self.updateDir('')

        self.setColumnWidth(0, 200)
        print('create local directory')

    def updateDir(self, directory):
        # 保存位置
        g_conf['localdir'] = directory
        self._curdir = directory
        g_conf.saveCfg()

        # 创建文件系统 model
        self._dirModel = QFileSystemModel()
        self._dirModel.setRootPath(directory)
        self.setModel(self._dirModel)
        index = self._dirModel.index(directory)

        # 设置目录位置，点击处理函数
        self.setRootIndex(index)
        self.clicked.connect(self._selectLocal)

    def _selectLocal(self, signal):
        self._filePath = self.model().filePath(signal)

    @property
    def curdir(self):
        return self._curdir

    @property
    def lfile(self):
        return self._filePath


class  CheckServStatusThread(threading.Thread):
    def __init__(self, servsList, mutex, interval=10):
        '''
        interval: 检查的间隔秒数
        '''
        super().__init__()
        self._interval = interval
        self._mutex = mutex
        self._servs = servsList
        self.daemon = True
        self._lasttime = datetime.datetime.now().timestamp()

    def run(self):
        print('start check ...{}'.format(self._lasttime))
        while True:
            time.sleep(1)
            curtime = datetime.datetime.now().timestamp()
            if curtime - self._lasttime > self._interval:
                self._lasttime = curtime
                print('cur time ...{}'.format(self._lasttime))
                servsTmp = ODict()
                with self._mutex:
                    servsTmp = copy.copy(self._servs)

                for serv in servsTmp.values():
                    servConn = Connection(host=serv[1],
                                          port=serv[2],
                                          user=serv[3],
                                          connect_kwargs={'password': serv[4]},
                                          connect_timeout=5)
                    def task():
                        result = servConn.run('ls {} | head -3'.format(serv[5]), hide=True)
                        # print(result)

                        if result.ok:
                            serv[6] = 'good'
                            serv[7] = '无'
                        else:
                            serv[6] = 'bad'
                            serv[7] = result.stdout.strip()[:256]
                    try:
                        task()
                        print(serv)
                    except (Exception, SystemExit) as e:
                        print(e)
                        serv[6] = 'bad'
                        serv[7] = str(e)

                with self._mutex:
                    print(servsTmp)
                    self._servs.update(servsTmp)


class RemoteServersList(QTreeWidget):
    def __init__(self, parent):
        super().__init__()
        self._parent = parent
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.itemClicked.connect(self.clicked)
        self.itemDoubleClicked.connect(self.doubleClicked)
        self.setColumnCount(6)
        self.setHeaderLabels(['名称', '主机', '端口', '路径', '状态', '问题描述'])
        self.setColumnWidth(1, 200)
        self._datas = ODict(g_conf.get('remoteServs', {}))
        self._mutex = threading.Lock()
        self._updateUI()
        self._checkThr = CheckServStatusThread(self._datas, self._mutex)
        self._checkThr.start()
        self._updateUIStatus()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._updateUIStatus)
        self._timer.start(10000)
        self._remoteServDirs = []
        self._remoteServFiles = []
        print('create remote servers list')

    def _statusLabel(self, status, question='无'):
        if status == 'good':
            color = 'green'
            text = u'可用'
        elif status == 'check':
            color = 'blue'
            text = u'检测中'
        else:
            color = 'red'
            text = u'不可用'
        return (QLabel('<font color="{}">{}</font>'.format(color, text)),
                QLabel('<font color="{}">{}</font>'.format(color, question)))

    def _updateUI(self):
        # self._checkStatus()
        # print('datas {}'.format(self._datas))
        with self._mutex:
            self.clear()
            for item in self._datas.values():
                treeWidgetItem = QTreeWidgetItem()
                self.addTopLevelItem(treeWidgetItem)
                self.setItemWidget(treeWidgetItem, 0, QLabel(item[0]))
                self.setItemWidget(treeWidgetItem, 1, QLabel(item[1]))
                self.setItemWidget(treeWidgetItem, 2, QLabel(item[2]))
                self.setItemWidget(treeWidgetItem, 3, QLabel(item[5]))
                status, question = self._statusLabel(item[6], item[6])
                self.setItemWidget(treeWidgetItem, 4, status)
                self.setItemWidget(treeWidgetItem, 5, question)

    def _updateUIStatus(self):
        with self._mutex:
            itemStatus = {data[0]: (data[6], data[7]) for data in self._datas.values()}
            # print(itemStatus)
            for i in range(self.topLevelItemCount()):
                treeWidgetItem = self.topLevelItem(i)
                name = self.itemWidget(treeWidgetItem, 0).text()
                status, question = self._statusLabel(itemStatus[name][0], itemStatus[name][1])
                if name in itemStatus:
                    self.setItemWidget(treeWidgetItem, 4, status)
                    self.setItemWidget(treeWidgetItem, 5, question)

    def getRows(self):
        rows = []
        with self._mutex:
            items = self.selectedItems()
            for item in items:
                nameLabel = self.itemWidget(item, 0)
                rows.append(self._datas[nameLabel.text()][1:])

        return rows

    def addHost(self, serv):
        '''
        serv: (name, host, port, user, passwd, path)
        '''
        with self._mutex:
            check = [True for i in serv if i]
            # print('update {}'.format(serv))
            if check.count(True) == 6:
                serv = list(serv)
                serv.append('check')
                serv.append('无')
                print(serv)
                self._datas[serv[0]] = serv

                # 自动存储配置
                g_conf['remoteServs'] = self._datas
                g_conf.saveCfg()
            else:
                print('missing information!')

        self._updateUI()


    def removeHost(self):
        with self._mutex:
            for item in self.selectedItems():
                nameLabel = self.itemWidget(item, 0).text()
                del self._datas[nameLabel]
                self.removeItemWidget(item, 0)
                g_conf['remoteServs'] = self._datas
                g_conf.saveCfg()
        self._updateUI()

    def clicked(self, item):
        nameLabel = self.itemWidget(item, 0).text()
        if nameLabel in self._datas:
            serv = self._datas[nameLabel]
            if serv[6] != 'good':
                self._parent.clearRemoteList()
                return

            def getServFileList(curDir):
                remoteLabel = '{}:{}'.format(serv[0], curDir)
                self._parent.setRemoteLabel(remoteLabel)
                serv[5] = curDir
                self.setItemWidget(item, 3, QLabel(curDir))

                # 获取远端服务器目录文件列表
                def getList(command):
                    try:
                        servConn = Connection(host=serv[1],
                                              port=serv[2],
                                              user=serv[3],
                                              connect_kwargs={'password': serv[4]},
                                              connect_timeout=10)
                        result = servConn.run(command, hide=True)
                    except Exception as error:
                        print(error)

                    if 'result' in locals() and result.ok:
                            return result.stdout.strip().split('\n')
                    else:
                        return []


                self._remoteServDirs = getList('cd {} && find . -type d -maxdepth 1'.format(curDir))
                self._remoteServFiles = getList('cd {} && find . -type f -maxdepth 1'.format(curDir))
                self._remoteServDirs = ['..' if len(i) == 1 else i[2:] for i in self._remoteServDirs] 
                self._remoteServFiles = ['..' if len(i) == 1 else i[2:] for i in self._remoteServFiles]

                if not self._remoteServDirs:
                    self._remoteServDirs = ['..']
                if not self._remoteServFiles:
                    self._remoteServFiles = ['..']
                return self._remoteServDirs, self._remoteServFiles

            self._parent.setRemoteList(serv[5], getServFileList)


    def doubleClicked(self, item):
        nameLabel = self.itemWidget(item, 0).text()
        if nameLabel in self._datas:
            serv = self._datas[nameLabel]
            # print(serv)
            hostDialog = HostDialog(self,
                                    name=serv[0],
                                    host=serv[1],
                                    port=serv[2],
                                    user=serv[3],
                                    passwd=serv[4],
                                    path=serv[5])
            serv = hostDialog.getServ()
            if serv:
                self.addHost(serv)


class HostDialog(QDialog):
    def __init__(self, parent, **values):
        super().__init__(parent)
        self._serv = None
        mainLayout = self.setEdit(**values)
        self.show(mainLayout)

    def setEdit(self, **values):
        mainLayout = QVBoxLayout(self)

        inputLayout = QGridLayout()

        servNameLabel = QLabel('serv name')
        if 'name' in values:
            self._servNameLineEdit = QLineEdit(values['name'])
        else:
            self._servNameLineEdit = QLineEdit()
        inputLayout.addWidget(servNameLabel, 0, 0, Qt.AlignRight)
        inputLayout.addWidget(self._servNameLineEdit, 0, 1)

        hostLabel = QLabel('host')
        if 'host' in values:
            self._hostLineEdit = QLineEdit(values['host'])
        else:
            self._hostLineEdit = QLineEdit()
        inputLayout.addWidget(hostLabel, 1, 0, Qt.AlignRight)
        inputLayout.addWidget(self._hostLineEdit, 1, 1)

        portLabel = QLabel('port')
        if 'port' in values:
            self._portLineEdit = QLineEdit(values['port'])
        else:
            self._portLineEdit = QLineEdit()
        inputLayout.addWidget(portLabel, 2, 0, Qt.AlignRight)
        inputLayout.addWidget(self._portLineEdit, 2, 1)

        userLabel = QLabel('user')
        if 'user' in values:
            self._userLineEdit = QLineEdit(values['user'])
        else:
            self._userLineEdit = QLineEdit()
        inputLayout.addWidget(userLabel, 3, 0, Qt.AlignRight)
        inputLayout.addWidget(self._userLineEdit, 3, 1)

        passwdLabel = QLabel('passwd')
        if 'passwd' in values:
            self._passwdLineEdit = QLineEdit(values['passwd'])
        else:
            self._passwdLineEdit = QLineEdit()
        inputLayout.addWidget(passwdLabel, 4, 0, Qt.AlignRight)
        inputLayout.addWidget(self._passwdLineEdit, 4, 1)

        pathLabel = QLabel('path')
        if 'path' in values:
            self._pathLineEdit = QLineEdit(values['path'])
        else:
            self._pathLineEdit = QLineEdit()
        inputLayout.addWidget(pathLabel, 5, 0, Qt.AlignRight)
        inputLayout.addWidget(self._pathLineEdit, 5, 1)

        hBtnLayout = QHBoxLayout()
        accept = QButton('保存')
        cancel = QButton('取消')
        hBtnLayout.addWidget(accept)
        hBtnLayout.addWidget(cancel)
        accept.clicked.connect(lambda _: self.acceptClick())
        cancel.clicked.connect(lambda _: self.reject())

        mainLayout.addLayout(inputLayout)
        mainLayout.addLayout(hBtnLayout)

        return mainLayout

    def acceptClick(self):
        path = self._pathLineEdit.text()
        if len(path) > 2 and path[-1] in ['/', '\\']:
            path = path[:-1]

        self._serv = (self._servNameLineEdit.text(),
                      self._hostLineEdit.text(),
                      self._portLineEdit.text(),
                      self._userLineEdit.text(),
                      self._passwdLineEdit.text(),
                      path)

        check = [True for i in self._serv if i]
        if check.count(True) == 6:
            self.accept()
        else:
            QMessageBox.warning(self,
                                '错误',
                                '缺少必须填写的信息！',
                                QMessageBox.Ok,
                                QMessageBox.Ok)


    def show(self, mainLayout):
        self.setLayout(mainLayout)

        font = QFont()
        font.setPointSize(12)
        self.setFont(font)
        self.setWindowTitle('增加服务器')
        self.setGeometry(400, 400, 1200, 1200)
        self.setSizeGripEnabled(False)
        self.setMinimumSize(800, 440)
        self.setMaximumSize(800, 440)
        ret = self.exec()


    def getServ(self):
        return self._serv


class RemoteServFileList(QTreeWidget):
    def __init__(self):
        super().__init__()
        self._curDir = None
        self.setColumnCount(2)
        self.setHeaderLabels(['', '名称'])
        self.setColumnWidth(1, 200)
        self.itemDoubleClicked.connect(self.doubleClicked)

    def doubleClicked(self, item):
        selected = self.itemWidget(item, 0).text()
        if selected in self._dirs and self._curDir:
            if selected == '..':
                self._curDir = self._curDir[:self._curDir.rfind('/')]
            else:
                if self._curDir == '/':
                    self._curDir = '/{}'.format(selected)
                else:
                    self._curDir = '{}/{}'.format(self._curDir, selected)

            if self._curDir == '':
                self._curDir = '/'

            print(selected, self._curDir)
            self.setRemoteList(self._curDir)

    def setRemoteList(self, curDir, getServFileList=None):
        self._curDir = curDir
        if getServFileList:
            self._getServFileList = getServFileList

        self._dirs, self._files = self._getServFileList(curDir)
        self.clear()
        icon = self.style().standardIcon(QStyle.SP_DirIcon)
        for curDir in self._dirs:
            treeWidgetItem = QTreeWidgetItem()
            treeWidgetItem.setIcon(0, icon)
            self.addTopLevelItem(treeWidgetItem)
            self.setItemWidget(treeWidgetItem, 0, QLabel(curDir))

        iconFile = self.style().standardIcon(QStyle.SP_FileIcon)
        for curFile in self._files:
            treeWidgetItem = QTreeWidgetItem()
            treeWidgetItem.setIcon(0, iconFile)
            self.addTopLevelItem(treeWidgetItem)
            self.setItemWidget(treeWidgetItem, 0, QLabel(curFile))

        self.expandAll()


class UTranMain(QMainWindow):
    def __init__(self):
        super().__init__()

        self.__setting = {}
        self.initUI()
        self.preView = False
        
    def initUI(self):
        # 工具栏，列表
        mainLayout = QVBoxLayout()

        openLocalAction = QAction('local', self)
        openLocalAction.triggered.connect(self._openLocalFile)
        # exitAction = QAction('remote', self)
        # exitAction.triggered.connect(self._quit)

        # 添加主机信息
        # addhostAction = QAction('hosts', self)
        # addhostAction.triggered.connect(self._addHost)

        exitAction = QAction('Exit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.triggered.connect(self._quit)

        self.toolbar = self.addToolBar('tools')
        self.toolbar.addAction(openLocalAction)
        # self.toolbar.addAction(addhostAction)
        self.toolbar.addAction(exitAction)

        # 创建主界面
        splitter = QSplitter(self)

        # 水平分割，文件目录列表，左侧：本地的文件，右侧：远端的文件
        # 左右布局
        leftLayout = QSplitter(Qt.Vertical, splitter)
        rightLayout = QSplitter(Qt.Vertical, splitter)

        # 目录路径标签
        self._localDirLabel = QLabel()
        self._remoteDirLabel = QLabel()

        # 目录内容展示
        self._localTreeLayout = LocalDirTree()
        self._localDirLabel.setText(self._localTreeLayout.curdir)
        self._remoteListLayout = RemoteServFileList()
        leftLayout.addWidget(self._localDirLabel)
        leftLayout.addWidget(self._localTreeLayout)
        self._localDirLabel.setMaximumHeight(40)
        leftLayout.setStretchFactor(0, 0)

        # 文件传送按钮
        self._uploadDataBtn = QButton('上传 =>')
        self._uploadDataBtn.setMaximumHeight(40)
        self._uploadDataBtn.clicked.connect(self._upload)
        self._downloadDataBtn = QButton('下载 <=')
        self._downloadDataBtn.setMaximumHeight(40)
        self._downloadDataBtn.clicked.connect(self._download)
        self._addHostBtn = QButton('增加服务器')
        self._addHostBtn.setMaximumHeight(40)
        self._addHostBtn.clicked.connect(self._addHost)
        self._removeHostBtn = QButton('删除服务器')
        self._removeHostBtn.setMaximumHeight(40)
        self._removeHostBtn.clicked.connect(self._removeHost)
        btnLayout = QSplitter(Qt.Horizontal, splitter)
        btnLayout.addWidget(self._uploadDataBtn)
        btnLayout.addWidget(self._downloadDataBtn)
        btnLayout.addWidget(self._addHostBtn)
        btnLayout.addWidget(self._removeHostBtn)
        rightLayout.addWidget(btnLayout)

        # 远端服务器列表
        self._remoteServersList = RemoteServersList(self)
        rightLayout.addWidget(self._remoteServersList)
        self._remoteServersList.setMaximumHeight(400)

        # 当前选择的远端服务器文件列表
        rightLayout.addWidget(self._remoteDirLabel)
        self._remoteDirLabel.setMaximumHeight(40)
        rightLayout.addWidget(self._remoteListLayout)

        leftLayout.setMinimumWidth(600)
        splitter.addWidget(leftLayout)
        splitter.addWidget(rightLayout)

        # 添加主界面控件
        self.setCentralWidget(splitter)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        # 设置界面大小
        font = QFont()
        font.setPointSize(12)
        self.setFont(font)
        # self.setGeometry(400, 400, 1800, 1600)
        # self.resize(1200, 800)
        self.setWindowState(Qt.WindowMaximized)
        self.setWindowTitle('UTran')
        self.show()

    def _addHost(self):
        hostDialog = HostDialog(self)
        serv = hostDialog.getServ()
        if serv:
            self._remoteServersList.addHost(serv)

    def _removeHost(self):
        buttonBox = QMessageBox()
        buttonBox.setText('确认删除服务器信息？')
        buttonBox.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel);
        ret = buttonBox.exec()
        if ret == QMessageBox.Ok:
            self._remoteServersList.removeHost()

    def _quit(self):
        g_conf.saveCfg()
        qApp.quit()

    def _openLocalFile(self):
        if not hasattr(self, '_localDir'):
            self._localDir = {'localDir': QDir.homePath()}
        localDir = QFileDialog.getExistingDirectory(self,
                                                    '打开本地目录',
                                                    self._localDir['localDir'])
        if not localDir:
            return
        self._localDir['localDir'] = localDir
        self._localTreeLayout.updateDir(localDir)
        print(self._localDir['localDir'])
        self._localDirLabel.setText(localDir)

    def _upload(self):
        if not self._localTreeLayout.lfile:
            return

        servs = self._remoteServersList.getRows()
        for serv in servs:
            servConn = Connection(host=serv[0],
                                  port=serv[1],
                                  user=serv[2],
                                  connect_kwargs={'password': serv[3]},
                                  connect_timeout=5)
            def task():
                remoteFile = os.path.basename(self._localTreeLayout.lfile)
                result = servConn.put(self._localTreeLayout.lfile,
                             '%s/%s' % (serv[4], remoteFile))
                # print(result)
                # put('/root/abc', '/home/user')

            try:
                task()
            except Exception as e:
                print(e)

    def _download(self):
        # print(self._localTreeLayout.lfile)
        pass

    def _openFile(self):
        if not hasattr(self, '_localDir'):
            self._localDir = {'localDir': QDir.homePath()}
        localDir = QFileDialog.getExistingDirectory(self,
                                                    '打开本地目录',
                                                    self._localDir['localDir'])
        if localDir:
            allFiles = os.listdir(localDir)
            print(localDir)
            subDirs = []
            subFiles = []
            for curFile in allFiles:
                absPath = '{}/{}'.format(localDir, curFile)
                if os.path.isdir(absPath):
                    subFiles.append(curFile)
                    print('dir: {}'.format(curFile))
                else:
                    subFiles.append(curFile)
                    print('file: {}'.format(curFile))
        self._localDir = {'localDir': localDir,
                          'subDirs': subDirs,
                          'subFiles': subFiles}

    def setRemoteLabel(self, label):
        self._remoteDirLabel.setText(label)

    def setRemoteList(self, curDir, getServFileList):
        self._remoteListLayout.setRemoteList(curDir, getServFileList)

    def clearRemoteList(self):
        self._remoteListLayout.clear()


if __name__ == '__main__':
    try:
        app = QApplication(sys.argv)
        utran_main = UTranMain()
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        print('--- KeyboardInterrupt ---')
    except Exception as error:
        print('have error')
        print(error)

    sys.exit('0')
