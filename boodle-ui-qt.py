#!/usr/bin/python2

# Boodler: a programmable soundscape tool
# Designed by Andrew Plotkin <erkyrath@eblong.com>
# For more information, see <http://boodler.org/>
#
# This Python script ("boodle-ui-qt.py") is licensed under the GNU
# Library General Public License (LGPL).
# Author: Tuukka Hastrup <Tuukka.Hastrup@iki.fi>
#
# You should have received a copy of the GNU Library General Public License
# along with this program. (It should be a document entitled "LGPL".)
# If not, see the web URL above, or write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import sys
import os, signal
from os.path import expanduser
import boodle
from boodle import agent, generator, builtin
import multiprocessing
import threading

sys.path.append('/usr/lib/python2.7/site-packages')

import boopak
from boopak import collect # you'll need Boodler on Python's library path

# same as in boodler.py
if 'darwin' in sys.platform.lower():
    Default_Relative_Data_Dir = '~/Library/Application Support/Boodler'
else:
    Default_Relative_Data_Dir = '~/.boodler'

basedir = None # XXX opts.basedir
if not basedir:
    basedir = os.environ.get('BOODLER_DATA')
if not basedir:
    basedir = expanduser(Default_Relative_Data_Dir)

# collect the list of agents

l = collect.PackageCollection(basedir=basedir)

pkgs = l.list_all_current_packages()

agents = []

for pkgname,_vers in sorted(pkgs):
    pkg = l.load(pkgname)
    for resname in sorted(pkg.resources.keys()):
        res = pkg.resources.get(resname)
        if res.get_one("boodler.use") == "agent":
            agents += [(pkgname, resname)]

audio_driver = 'portaudio'

def procmain(basedir, agent):
    coldir = os.path.join(basedir, boopak.collect.Filename_Collection)
    loader = boopak.pload.PackageLoader(coldir, importing_ok=True)
    clas = boodle.agent.load_described(loader, agent)
    ag = clas()
    gen = generator.Generator(0.5, False, False, None, loader=loader)
    gen.addagent(ag, gen.rootchannel, 0, ag.run)
    cboodle = boodle.set_driver(audio_driver)
    cboodle.init(None, 0, False, {})
    cboodle.loop(generator.run_agents, gen)
    cboodle.final()

def play(agent):
    proc = multiprocessing.Process(target=procmain, args=(basedir, "%s/%s" % agent))
    proc.start()
    return proc

def threadmain(win):
    proc = win.boodler
    proc.join()
    win.playFinished(proc.exitcode)

def qtmain():
    from PyQt4 import QtCore, QtGui # you'll need PyQt4 (python-qt4)

    def index2rowdata(index):
        rowdata = (index.sibling(index.row(), 0).data().toString(),
                   index.sibling(index.row(), 1).data().toString(),
                   index.sibling(index.row(), 2).data().toString(),
                   )

        return rowdata

    class Window(QtGui.QWidget):
        def __init__(self, app):
            self.boodler = None

            QtGui.QWidget.__init__(self)

            self.connect(app, QtCore.SIGNAL('aboutToQuit()'), self.stopPlay)

            # proxy model for sorting and filtering
            self.proxyModel = QtGui.QSortFilterProxyModel()
            self.proxyModel.setDynamicSortFilter(True)
            self.proxyModel.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)
            self.proxyModel.setFilterKeyColumn(2)

            # widgets for now playing agent
            self.nowPlayingGroupBox = QtGui.QGroupBox("Now playing")
            self.nowPlayingLabel = QtGui.QLabel("Double-click a soundscape to play\n")
            self.nowPlayingButton = QtGui.QPushButton(self.style().standardIcon(QtGui.QStyle.SP_MediaStop), "&Stop")
            self.nowPlayingButton.setEnabled(False)

            # signals for now playing agent
            self.connect(self.nowPlayingButton, QtCore.SIGNAL('clicked()'), self.stopPlay)

            # widgets for selected agent
            self.selectedGroupBox = QtGui.QGroupBox("Selected soundscape")
            self.selectedLabel = QtGui.QLabel("Click a soundscape to view details\n")
            self.selectedInfoLabel = QtGui.QLabel("Internal name:\nLicense:\nSource:")
            self.selectedButton = QtGui.QPushButton(self.style().standardIcon(QtGui.QStyle.SP_MediaPlay), "&Play")
            self.selectedButton.setEnabled(False)

            # signals for now playing agent
            self.connect(self.selectedButton, QtCore.SIGNAL('clicked()'), self.playButtonClicked)

            # view widgets
            self.proxyGroupBox = QtGui.QGroupBox("Available soundscapes")

            self.proxyView = QtGui.QTreeView()
            self.proxyView.setRootIsDecorated(False)
            self.proxyView.setAlternatingRowColors(True)
            self.proxyView.setModel(self.proxyModel)
            self.proxyView.setSortingEnabled(True)
            self.proxyView.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
            self.proxyView.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
            self.proxyView.setAllColumnsShowFocus(True)

            # filter pattern widgets
            self.filterPatternLineEdit = QtGui.QLineEdit()
            self.filterPatternLabel = QtGui.QLabel("F&ind:")
            self.filterPatternLabel.setBuddy(self.filterPatternLineEdit)

            # filter pattern signals
            self.connect(self.filterPatternLineEdit,
                    QtCore.SIGNAL('textChanged(const QString &)'),
                    self.filterRegExpChanged)

            self.connect(self.proxyView.selectionModel(),
                         QtCore.SIGNAL('currentRowChanged(const QModelIndex &, const QModelIndex &)'),
                         self.itemSelected)
            self.connect(self.proxyView, QtCore.SIGNAL('activated(const QModelIndex &)'), self.itemActivated)

            # now playing layout
            nowPlayingLayout = QtGui.QHBoxLayout()
            nowPlayingLayout.addWidget(self.nowPlayingButton)
            nowPlayingLayout.addWidget(self.nowPlayingLabel, 1)
            self.nowPlayingGroupBox.setLayout(nowPlayingLayout)

            # selected layout
            selectedLayout = QtGui.QVBoxLayout()
            selectedLayoutH = QtGui.QHBoxLayout()
            selectedLayoutH.addWidget(self.selectedButton)
            selectedLayoutH.addWidget(self.selectedLabel, 1)
            selectedLayout.addLayout(selectedLayoutH)
            selectedLayout.addWidget(self.selectedInfoLabel)
            self.selectedGroupBox.setLayout(selectedLayout)

            # available agents layout
            filterPatternLayout = QtGui.QHBoxLayout()
            filterPatternLayout.addWidget(self.filterPatternLabel)
            filterPatternLayout.addWidget(self.filterPatternLineEdit)

            proxyLayout = QtGui.QVBoxLayout()
            proxyLayout.addWidget(self.proxyView)
            proxyLayout.addLayout(filterPatternLayout)
            self.proxyGroupBox.setLayout(proxyLayout)

            # main layout
            mainLayout = QtGui.QVBoxLayout()
            mainLayout.addWidget(self.nowPlayingGroupBox)
            mainLayout.addWidget(self.selectedGroupBox)
            mainLayout.addWidget(self.proxyGroupBox)
            self.setLayout(mainLayout)

            # set top-level window properties
            self.setWindowTitle("Boodle UI")
            self.resize(500, 450)

            # set initial state
            self.proxyView.sortByColumn(2, QtCore.Qt.AscendingOrder)
            self.filterPatternLineEdit.setText("")

        def setSourceModel(self, model):
            self.proxyModel.setSourceModel(model)

        def filterRegExpChanged(self):
            regExp = QtCore.QRegExp(self.filterPatternLineEdit.text(), QtCore.Qt.CaseInsensitive, QtCore.QRegExp.Wildcard)
            self.proxyModel.setFilterRegExp(regExp)

        def itemSelected(self, currentIndex, _previousIndex):
            if not currentIndex.isValid():
                return # keep the latest selection, if any
            row = index2rowdata(currentIndex)
            self.lastSelectedRow = row
            self.selectedButton.setEnabled(True)
            self.updateSelected(row)

        def itemActivated(self, index):
            row = index2rowdata(index)
            self.startPlay((str(row[0]), str(row[1])))
            self.updateNowPlaying(row)

        def playButtonClicked(self):
            row = self.lastSelectedRow
            self.startPlay((str(row[0]), str(row[1])))
            self.updateNowPlaying(row)

        def updateNowPlaying(self, row):
            pkg = l.load(str(row[0]))
            creator = pkg.metadata.get_one("dc.creator")
            pkgtitle = pkg.metadata.get_one("dc.title")

            msg = '"%s"\nby %s from "%s"' % (row[2], creator, pkgtitle)
            self.nowPlayingLabel.setText(msg)

        def updateSelected(self, row):
            pkg = l.load(str(row[0]))
            creator = pkg.metadata.get_one("dc.creator")
            pkgtitle = pkg.metadata.get_one("dc.title")
            license = pkg.metadata.get_one("dc.license")
            source = pkg.metadata.get_one("dc.source")

            msg = '"%s"\nby %s from "%s"' % (row[2], creator, pkgtitle)
            self.selectedLabel.setText(msg)

            info = 'Internal name: %s/%s' % (row[0], row[1])
            info += '\nLicense: %s' % license
            info += '\nSource: %s' % source
            self.selectedInfoLabel.setText(info)


        def startPlay(self, agent):
            self.stopPlay()

            self.boodler = play(agent)
            thread = threading.Thread(target=threadmain, args=(self,))
            thread.start()

            self.nowPlayingButton.setEnabled(True)

        def stopPlay(self):
            if self.boodler:
                if self.boodler.is_alive():
                    self.boodler.terminate()
                self.boodler = None

            self.nowPlayingButton.setEnabled(False)

        def playFinished(self, exitCode):
            if exitCode > 0:
                print "Boodler failed with exit code %s." % exitCode
            else:
                print "Boodler done playing."

            self.stopPlay()

    def createAgentModel(parent):
        model = QtGui.QStandardItemModel(0, 3, parent)

        model.setHeaderData(0, QtCore.Qt.Horizontal, QtCore.QVariant("Package"))
        model.setHeaderData(1, QtCore.Qt.Horizontal, QtCore.QVariant("Resource"))
        model.setHeaderData(2, QtCore.Qt.Horizontal, QtCore.QVariant("Title"))

        def standardItem(x):
            if x is None:
                return QtGui.QStandardItem("")
            else:
                return QtGui.QStandardItem(x)

        for agent in reversed(agents):
            pkg = l.load(agent[0])
            res = pkg.resources.get(agent[1])
            title = res.get_one("dc.title")
            model.appendRow(map(standardItem, [agent[0], agent[1], title]))

        return model

    app = QtGui.QApplication(sys.argv)
    window = Window(app)
    window.setSourceModel(createAgentModel(window))
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    qtmain()
