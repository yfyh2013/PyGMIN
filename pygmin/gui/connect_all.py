import sys
import time
import numpy as np
import sqlalchemy

from PyQt4 import QtGui, QtCore, Qt

from pygmin.gui.double_ended_connect_runner import DECRunner
from pygmin.landscape import TSGraph
from pygmin.gui.connect_run_dlg import ConnectViewer
from pygmin.gui.ui.dgraph_dlg import DGraphWidget
from pygmin.storage import Minimum

class ConnectAttempt(object):
    def __init__(self, min1, min2, success, minima, transition_states, elapsed_time=None):
        self.min1 = min1
        self.min2 = min2
        self.success = success
        self.minima = minima
        self.transition_states = transition_states
        self.time = elapsed_time
 

class ConnectAllSummary(object):
    def __init__(self):
        self.attempts = []
    
    def add(self, min1, min2, success, minima, transition_states, **kwargs):
        attempt = ConnectAttempt(min1, min2, success, minima, transition_states, **kwargs)
        self.attempts.append(attempt)
    
    def get_summary(self):
        summary = ""
        summary += "%d connect attempts\n" % len(self.attempts)
        successes = [ca for ca in self.attempts if ca.success]
        summary += "%d successes %d failures\n" % (len(successes), len(self.attempts) - len(successes))
        nminima = sum([len(ca.minima) for ca in self.attempts]) 
        nts = sum([len(ca.transition_states) for ca in self.attempts])
        summary += "%d minima and %d transition states found\n" % (nminima, nts)
        total_time = sum([ca.time for ca in self.attempts])
        summary += "%.2f total time\n" % total_time
        
        summary += "\n"
        for ca in self.attempts:
            if ca.success:
                success = "success"
            else:
                success = "fail   " 
            summary += "%d <--> %d: %s, time %.2f\n" % (ca.min1._id, ca.min2._id, success, ca.time)
        return summary
        

class ConnectAllDialog(ConnectViewer):
    def __init__(self, system, database, parent=None, app=None):
        super(ConnectAllDialog, self).__init__(system, database, app=app, parent=parent)

        self.wgt_dgraph = DGraphWidget(database=self.database, parent=self)
        self.view_dgraph = self.new_view("Disconnectivity Graph", self.wgt_dgraph, QtCore.Qt.TopDockWidgetArea)
        self.view_dgraph.hide()
        self.ui.actionD_Graph.setVisible(True)
        self.ui.actionD_Graph.setChecked(False)

        self.textEdit_summary = QtGui.QTextEdit(parent=self)
        self.textEdit_summary.setReadOnly(True)
        self.view_summary = self.new_view("Summary", self.textEdit_summary, pos=QtCore.Qt.TopDockWidgetArea)
        self.connect_summary = ConnectAllSummary()
        self.ui.actionSummary.setVisible(True)
        self.view_summary.hide()
        self.ui.actionSummary.setChecked(False)
        self.ui.actionRandom_connect.setVisible(True)
        self.ui.actionRandom_connect.setChecked(False)

        

        self.ui.action3D.setChecked(False)
        self.view_3D.hide()
        
        self.ui.actionEnergy.setChecked(False)
        self.view_energies.hide()
        
        self.ui.actionPause.setVisible(True)
        
        self.is_running = False
        
        self.failed_pairs = set()
    


    def do_one_connection(self, min1, min2):
        self.textEdit.insertPlainText("\n\n")
        self.textEdit_summary.insertPlainText("\nNow connecting minima %d %d\n" % (self.min1._id, self.min2._id))
        self.decrunner = DECRunner(self.system, self.database, min1, min2, outstream=self.textEdit_writer,
                                   return_smoothed_path=True)
        self.decrunner.on_finished.connect(self.on_finished)
        self.tstart = time.clock()
        self.decrunner.start()

    def get_next_pair_gmin(self):
        minima = self.database.minima()
        min1 = minima[0]
        graph = TSGraph(self.database)
        all_connected = True
        for m2 in minima[1:]:
            if not graph.areConnected(min1, m2):
                if (min1, m2) in self.failed_pairs or (m2, min1) in self.failed_pairs:
                    continue
                all_connected = False
                break
        if all_connected:
            print "minima are all connected, ending"
            self.textEdit_summary.insertPlainText("minima are all connected, ending\n")
            return None, None
        return min1, m2

    def get_next_pair_random(self):
        ''' get a new connect job '''
        query =  self.database.session.query(Minimum)
#        if self.Emax is not None:
#            query.filter(Minimum.energy < self.Emax)
        
        while True:
            min1 = query.order_by(sqlalchemy.func.random()).first()
            min2 = query.order_by(sqlalchemy.func.random()).first()
            if (min1, min2) not in self.failed_pairs and (min2, min1) not in self.failed_pairs:
                return min1, min2
        
        


    def do_next_connect(self):
        self.is_running = True
        if self.ui.actionRandom_connect.isChecked():
            self.min1, self.min2 = self.get_next_pair_random()
        else:
            self.min1, self.min2 = self.get_next_pair_gmin()
        
        if self.min1 is None or self.min2 is None:
            self.is_running = False
            return
        self.do_one_connection(self.min1, self.min2)
        

    def start(self):
        self.do_next_connect()

    def update_energy_view(self):
        # plot the energies
        if self.view_energies.isVisible():
            self.wgt_energies.update_gui(self.S, self.energies)

    def update_graph_view(self):
        # show the graph view
        if self.view_graphview.isVisible():
            self.wgt_graphview.make_graph()
            self.wgt_graphview.show_graph()

    def update_3D_view(self):
        # show the smoothed path in the ogl viewer
        if self.view_3D.isVisible():
            self.ogl.setCoordsPath(self.smoothed_path)

    def update_dgraph_view(self):
        if self.view_dgraph.isVisible():
            self.wgt_dgraph.rebuild_disconnectivity_graph()

    def update_summary_view(self):
        self.textEdit_summary.clear()
        summary = self.connect_summary.get_summary()
        self.textEdit_summary.insertPlainText(summary)

    def on_finished(self):
        print "finished connecting", self.min1._id, "and", self.min2._id 
        tend = time.clock()
        elapsed_time = tend - self.tstart
#        print "\n"
        # add this run to the summary
        self.connect_summary.add(self.min1, self.min2, self.decrunner.success, 
                                 self.decrunner.newminima, self.decrunner.newtransition_states, elapsed_time=elapsed_time)
        
        if not self.isVisible():
            self.is_running = False
            return
        if self.decrunner.success:
            # get the path data
            self.smoothed_path = np.array(self.decrunner.smoothed_path)
            self.S = np.array(self.decrunner.S)
            self.energies = np.array(self.decrunner.energies)
#            print self.smoothed_path.shape


            self.update_3D_view()
            self.update_energy_view()
            self.update_graph_view()
            self.update_dgraph_view()
        else:
            print "connection run failed"
#            summary "connection run failed"
            if not self.decrunner.killed_early:
                self.failed_pairs.add( (self.min1, self.min2) )

        self.update_summary_view()
        if self.ui.actionPause.isChecked():
            self.is_running = False
            return
        self.do_next_connect()

    def on_actionEnergy_toggled(self, checked):
        self.toggle_view(self.view_energies, checked)
        self.update_energy_view()
    def on_actionGraph_toggled(self, checked):
        self.toggle_view(self.view_graphview, checked)
        self.update_graph_view()
    def on_action3D_toggled(self, checked):
        self.toggle_view(self.view_3D, checked)
        self.update_3D_view()
    def on_actionD_Graph_toggled(self, checked):
        self.toggle_view(self.view_dgraph, checked)
        self.update_dgraph_view()
    def on_actionSummary_toggled(self, checked):
        self.toggle_view(self.view_summary, checked)

    def on_actionPause_toggled(self, checked):
        if checked is None: return
        if not checked:
            if not self.is_running:
                self.start()
    
    def on_actionKill_triggered(self, checked=None):
        if checked is None: return
        self.ui.actionPause.setChecked(True)
        self.is_running = False
        self.decrunner.terminate_early()


#
# only testing below here
#

def start():
    wnd.start()

if __name__ == "__main__":
    from OpenGL.GLUT import glutInit
    import sys
    import pylab as pl

    app = QtGui.QApplication(sys.argv)
    from pygmin.systems import LJCluster, BLJCluster
    pl.ion()
    natoms = 13
    system = BLJCluster(natoms)
    system.params.double_ended_connect.local_connect_params.NEBparams.iter_density = 5.
    dbname = "lj%dtest.db" % (natoms,)
    db = system.create_database()#dbname)
    
    #get some minima
    if True:
        bh = system.get_basinhopping(database=db)
        bh.run(20)
        minima = db.minima()
    else:
        x1, e1 = system.get_random_minimized_configuration()[:2]
        x2, e2 = system.get_random_minimized_configuration()[:2]
        min1 = db.addMinimum(e1, x1)
        min2 = db.addMinimum(e2, x2)
        minima = [min1, min2]

    
    
    wnd = ConnectAllDialog(system, db, app=app)
#    decrunner = DECRunner(system, db, min1, min2, outstream=wnd.textEdit_writer)
    glutInit()
    wnd.show()
    from PyQt4.QtCore import QTimer
    QTimer.singleShot(100, start)
    sys.exit(app.exec_()) 
