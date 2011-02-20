
import numpy as N
import util
import unittest
import subprocess as SP
class TestUtil(unittest.TestCase):
    """Tests all of the functions in util.py
    
    To test all parallel features, use "mpiexec -n 2 python testutil.py"
    Some parallel features are tested even when running in serial.
    """
    
    def setUp(self):
        try:
            from mpi4py import MPI
            self.comm=MPI.COMM_WORLD
            self.numProcs = self.comm.Get_size()
            self.myMPI=util.MPI(numProcs=self.numProcs)
            self.rank = self.comm.Get_rank()
            self.mpi4py = True
        except ImportError:
            print 'WARNING - no mpi4py module, no parallel functionality tested'
            self.mpi4py=False
  
    def test_load_save_mat_text(self):
        """Test that can read/write text matrices"""
        tol = 8
        maxNumRows = 20
        maxNumCols = 8
        matPath = 'testMatrix.txt'
        delimiters = [',',' ',';']
        for delimiter in delimiters:
            for numRows in range(1,maxNumRows):
                for numCols in range(1,maxNumCols):
                    mat=N.random.random((numRows,numCols))
                    util.save_mat_text(mat,matPath,delimiter=delimiter)
                    matRead = util.load_mat_text(matPath,delimiter=delimiter)
                    N.testing.assert_array_almost_equal(mat,matRead,decimal=tol)
        SP.call(['rm',matPath])
        
    def test_MPI_init(self):
        """Test that the MPI object uses arguments correctly.
        
        Tests must be run in parallel (with mpiexec -n 2). Also test that
        when in serial, it defaults to a good behavior."""
        self.assertEqual(self.myMPI.numProcs,self.numProcs)
        self.assertEqual(self.myMPI.rank,self.rank)
        
        #Test that it is possible to use fewer CPUs than available
        if self.numProcs>1:
          mpiChangeCPUs = util.MPI(self.numProcs-1)
          self.assertEqual(mpiChangeCPUs.numProcs,self.numProcs-1)
        
        #Test that non-sensible values of CPUs are defaulted to num available.
        mpiZeroCPUs = util.MPI(numProcs=0)
        self.assertEqual(mpiZeroCPUs.numProcs,self.numProcs)
        mpiTooManyCPUs = util.MPI(numProcs=self.numProcs+1)
        self.assertEqual(mpiTooManyCPUs.numProcs,self.numProcs)
        
        
    
    def test_MPI_find_consec_proc_assignments(self):
        """Tests that the correct processor assignments are determined
        
        Given a range of consecutive numbers starting from 0, it tests
        that the correct assignment list is returned. Rather than requiring
        the testutil.py script to be run with many different numbers of procs,
        the behavior of this function is mimiced by manually setting numProcs.
        This should NEVER be done by a user!
        """
        
        numTasks = 10
        
        numProcs = 2
        correctAssignments = [0,5,10]
        self.myMPI.numProcs = numProcs
        self.assertEqual(self.myMPI.find_consec_proc_assignments(numTasks),
          correctAssignments)
        
        numProcs = 3
        correctAssignments = [0,4,8,10]
        self.myMPI.numProcs = numProcs
        self.assertEqual(self.myMPI.find_consec_proc_assignments(numTasks),
          correctAssignments)
          
        
        numProcs = 4
        correctAssignments = [0,3,6,9,10]
        self.myMPI.numProcs = numProcs
        self.assertEqual(self.myMPI.find_consec_proc_assignments(numTasks),
          correctAssignments)
        
        numProcs = 6
        correctAssignments = [0,2,4,6,8,10,10]
        self.myMPI.numProcs = numProcs
        self.assertEqual(self.myMPI.find_consec_proc_assignments(numTasks),
          correctAssignments)
          
        numProcs = 8
        correctAssignments = [0,2,4,6,8,10,10,10,10]
        self.myMPI.numProcs = numProcs
        self.assertEqual(self.myMPI.find_consec_proc_assignments(numTasks),
          correctAssignments)
    
    def test_MPI_find_proc_assignments(self):
        """Tests that the correct processor assignments are determined
        
        Given a list of tasks, it tests
        that the correct assignment list is returned. Rather than requiring
        the testutil.py script to be run with many different numbers of procs,
        the behavior of this function is mimiced by manually setting numProcs.
        This should NEVER be done by a user!
        """
        
        numTasks=15
        taskList = range(numTasks)
        numProcs = 4
        #Test that it gives the same output as consecutive assignments
        # for that special case
        self.myMPI.numProcs = numProcs
        consecAssignments = self.myMPI.find_consec_proc_assignments(numTasks)
        nonconsecAssignments = self.myMPI.find_proc_assignments(taskList)
        self.assertEqual(len(nonconsecAssignments),numProcs)
        
        for CPUNum in range(numProcs):
            self.assertEqual(nonconsecAssignments[CPUNum][0],\
              consecAssignments[CPUNum])
            self.assertEqual(nonconsecAssignments[CPUNum][-1],\
              consecAssignments[CPUNum+1]-1)
        
        #can handle a list of any type of objects
        taskList = ['1','2','4','8','16','32','64','128']
        numTasks = len(taskList)
        numProcs = 3
        self.myMPI.numProcs=numProcs
        correctAssignments=[['1','2','4'],['8','16','32'],['64','128']]
        self.assertEqual(self.myMPI.find_proc_assignments(taskList),
          correctAssignments)
        
        #more tests?
        
    
if __name__=='__main__':
    unittest.main()
