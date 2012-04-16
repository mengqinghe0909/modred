#!/usr/bin/env python

import os
from os.path import join
from shutil import rmtree
import copy
#import inspect #makes it possible to find information about a function
import unittest
import numpy as N
import random

import helper
helper.add_to_path('src')
import parallel as parallel_mod
parallel = parallel_mod.default_instance

from vecoperations import VecOperations
import vectors as V
import util

class TestVecOperations(unittest.TestCase):
    """ Tests of the VecOperations class """
    
    def setUp(self):
    
        if not os.access('.', os.W_OK):
            raise RuntimeError('Cannot write to current directory')
            
        self.test_dir = 'DELETE_ME_test_files_vecoperations'
        if not os.path.isdir(self.test_dir) and parallel.is_rank_zero():
            os.mkdir(self.test_dir)

        self.max_vecs_per_proc = 10
        self.total_num_vecs_in_mem = parallel.get_num_procs() * self.max_vecs_per_proc

        # VecOperations object for running tests
        self.my_vec_ops = VecOperations(inner_product=N.vdot, verbose=False)
        self.my_vec_ops.max_vecs_per_proc = self.max_vecs_per_proc

        # Default data members, verbose set to false even though default is true
        # so messages won't print during tests
        self.default_data_members = {'inner_product': N.vdot,
            'max_vecs_per_node': int(1e6),
            'max_vecs_per_proc': int(1e6) * parallel.get_num_nodes() / \
                parallel.get_num_procs(),
            'parallel':parallel_mod.default_instance,
            'verbose': False, 'print_interval': 10, 'prev_print_time': 0.}        
        parallel.sync()


    def tearDown(self):
        parallel.sync()
        if parallel.is_rank_zero():
            rmtree(self.test_dir, ignore_errors=True)
        parallel.sync()
 
 
    #@unittest.skip('testing other things')
    def test_init(self):
        """
        Test arguments passed to the constructor are assigned properly.
        """
        data_members_original = util.get_data_members(
            VecOperations(inner_product=N.vdot, verbose=False))
        self.assertEqual(data_members_original, self.default_data_members)
                
        max_vecs_per_node = 500
        my_VO = VecOperations(inner_product=N.vdot, 
            max_vecs_per_node=max_vecs_per_node, verbose=False)
        data_members = copy.deepcopy(data_members_original)
        data_members['max_vecs_per_node'] = max_vecs_per_node
        data_members['max_vecs_per_proc'] = max_vecs_per_node * \
            my_VO.parallel.get_num_nodes()/ my_VO.parallel.get_num_procs()
        self.assertEqual(util.get_data_members(my_VO), data_members)

        

    #@unittest.skip('testing other things')
    def test_idiot_check(self):
        """
        Tests idiot_check correctly checks user-supplied objects and functions.
        """
        nx = 40
        ny = 15
        test_array = N.random.random((nx,ny))
            
        my_VO = VecOperations(inner_product=N.vdot, verbose=False)
        in_mem_handle = V.InMemoryHandle(test_array)
        # Currently not testing this, there is a problem with max recursion
        # depth
        #self.assertRaises(RuntimeError, my_VO.idiot_check, in_mem_handle,
        #    max_handle_size=0)       
        my_VO.idiot_check(in_mem_handle, max_handle_size=1e6)
        
        # An idiot's vector that redefines multiplication to modify its data
        class IdiotMultVec(V.VectorBase):
            def __init__(self, arr):
                self.arr = arr
            def __add__(self, obj):
                f_return = copy.deepcopy(self)
                f_return.arr += obj.arr
                return f_return
            def __mul__(self, a):
                self.arr *= a
                return self
                
        class IdiotAddVec(V.VectorBase):
            def __init__(self, arr):
                self.arr = arr
            def __add__(self, obj):
                self.arr += obj.arr
                return self
            def __mul__(self, a):
                f_return = copy.deepcopy(self)
                f_return.arr *= a
                return f_return
        
        def my_IP(vec1, vec2):
            return N.vdot(vec1.arr, vec2.arr)
        my_VO.inner_product = my_IP
        my_idiot_mult_vec = IdiotMultVec(test_array)
        self.assertRaises(ValueError, my_VO.idiot_check, 
            V.InMemoryHandle(my_idiot_mult_vec), max_handle_size=1e6)
        my_idiot_add_vec = IdiotAddVec(test_array)
        self.assertRaises(ValueError, my_VO.idiot_check, 
            V.InMemoryHandle(my_idiot_add_vec), max_handle_size=1e6)
                
        
        
    def generate_vecs_modes(self, num_states, num_vecs, num_modes, index_from=1):
        """
        Generates random vecs and finds the modes. 
        
        Returns:
            vec_mat: matrix in which each column is a vec (in order)
            mode_nums: unordered list of integers representing mode numbers,
                each entry is unique. Mode numbers are picked randomly.
            build_coeff_mat: matrix num_vecs x num_modes, random entries
            mode_mat: matrix of modes, each column is a mode.
                matrix column # = mode_number - index_from
        """
        mode_nums = range(index_from, num_modes + index_from)
        random.shuffle(mode_nums)

        build_coeff_mat = N.mat(N.random.random((num_vecs, num_modes)))
        vec_mat = N.mat(N.zeros((num_states, num_vecs)))
        for vec_index in range(num_vecs):
            vec_mat[:,vec_index] = N.random.random((num_states, 1))
        mode_mat = vec_mat*build_coeff_mat
        return vec_mat, mode_nums, build_coeff_mat, mode_mat 
        
    
    
    #@unittest.skip('testing other things')
    def test_compute_modes(self):
        """Test that can compute modes from arguments. 
               
        Cases are tested for numbers of vecs, states per vec,
        mode numbers, number of vecs/modes allowed in memory
        simultaneously, and indexing schemes.
        """
        num_vecs_list = [1, 15, 40]
        num_states = 20
        # Test cases where number of modes:
        #   less, equal, more than num_states
        #   less, equal, more than num_vecs
        #   less, equal, more than total_num_vecs_in_mem
        num_modes_list = [1, 8, 10, 20, 25, 45, \
            int(N.ceil(self.total_num_vecs_in_mem / 2.)),\
            self.total_num_vecs_in_mem, self.total_num_vecs_in_mem * 2]
        index_from_list = [0, 5]
        mode_path = join(self.test_dir, 'mode_%03d.txt')
        vec_path = join(self.test_dir, 'vec_%03d.txt')
        
        for num_vecs in num_vecs_list:
            for num_modes in num_modes_list:
                for index_from in index_from_list:
                    #generate data and then broadcast to all procs
                    #print '----- new case ----- '
                    #print 'num_vecs =',num_vecs
                    #print 'num_states =',num_states
                    #print 'num_modes =',num_modes
                    #print 'max_vecs_per_node =',max_vecs_per_node                          
                    #print 'index_from =',index_from
                    vec_handles = [V.ArrayTextHandle(vec_path%i) 
                        for i in xrange(num_vecs)]

                    if parallel.is_rank_zero():
                        vec_mat, mode_nums, build_coeff_mat, true_modes = \
                          self.generate_vecs_modes(num_states, num_vecs,
                          num_modes, index_from=index_from)
                        for vec_index, vec_handle in enumerate(vec_handles):
                            vec_handle.put(vec_mat[:,vec_index])
                    else:
                        mode_nums = None
                        build_coeff_mat = None
                        vec_mat = None
                        true_modes = None
                    if parallel.is_distributed():
                        mode_nums = parallel.comm.bcast(mode_nums, root=0)
                        build_coeff_mat = parallel.comm.bcast(build_coeff_mat,
                            root=0)
                        vec_mat = parallel.comm.bcast(vec_mat, root=0)
                        true_modes = parallel.comm.bcast(true_modes, root=0)
                    
                    mode_handles = [V.ArrayTextHandle(mode_path%mode_num)
                        for mode_num in mode_nums]
                    # if any mode number (minus starting indxex)
                    # is greater than the number of coeff mat columns,
                    # or is less than zero
                    check_assert_raises = False
                    for mode_num in mode_nums:
                        mode_num_from_zero = mode_num-index_from
                        if mode_num_from_zero < 0 or mode_num_from_zero >=\
                            build_coeff_mat.shape[1]:
                            check_assert_raises = True
                    if check_assert_raises:
                        self.assertRaises(ValueError, self.my_vec_ops.\
                            _compute_modes, mode_nums, mode_handles, 
                            vec_handles, build_coeff_mat, index_from=\
                            index_from)
                    # If the coeff mat has more rows than there are 
                    # vec paths
                    elif num_vecs > build_coeff_mat.shape[0]:
                        self.assertRaises(ValueError, self.my_vec_ops.\
                            _compute_modes, mode_nums, mode_handles,
                            vec_handles, build_coeff_mat, index_from=\
                            index_from)
                    elif num_modes > num_vecs:
                        self.assertRaises(ValueError,
                          self.my_vec_ops.compute_modes, mode_nums,
                          mode_handles, vec_handles, build_coeff_mat,
                          index_from=index_from)
                    else:
                        # Remove this test, can't interpret what a user means?
                        # Can replace with a warning message
                        # Test the case that only one mode is desired,
                        # in which case user might pass in an int
                        if len(mode_nums) == 1:
                            mode_nums = mode_nums[0]
                            mode_handles = mode_handles[0]
                            
                        # Saves modes to files
                        self.my_vec_ops.compute_modes(mode_nums, 
                            mode_handles,
                            vec_handles, build_coeff_mat, 
                            index_from=index_from)

                        # Change back to list so is iterable
                        if not isinstance(mode_nums, list):
                            mode_nums = [mode_nums]

                        parallel.sync()
                        #print 'mode_nums',mode_nums
                        for mode_num in mode_nums:
                            computed_mode = V.ArrayTextHandle(
                                mode_path % mode_num).get()
                            #print 'mode number',mode_num
                            #print 'true mode',true_modes[:,\
                            #    mode_num-index_from]
                            #print 'computed mode',computed_mode
                            N.testing.assert_allclose(
                                computed_mode, true_modes[:,mode_num-\
                                index_from])
                                
                        parallel.sync()
       
        parallel.sync()
    
    #@unittest.skip('testing others')
    def test_compute_modes_return(self):
        """Tests that compute_modes returns the modes"""
        num_states = 21
        num_modes_list = [1, 5, 22]
        num_vecs = 30
        index_from = 1
        my_vec_ops = VecOperations(inner_product=N.vdot, verbose=False)
        for num_modes in num_modes_list:
            #generate data and then broadcast to all procs
            if parallel.is_rank_zero():
                vec_mat, mode_nums, build_coeff_mat, true_modes = \
                  self.generate_vecs_modes(num_states, num_vecs,
                  num_modes, index_from)
            else:
                mode_nums = None
                build_coeff_mat = None
                vec_mat = None
                true_modes = None
            if parallel.is_distributed():
                mode_nums = parallel.comm.bcast(mode_nums, root=0)
                build_coeff_mat = parallel.comm.bcast(build_coeff_mat, root=0)
                vec_mat = parallel.comm.bcast(vec_mat, root=0)
                true_modes = parallel.comm.bcast(true_modes, root=0)
                
            # Returns modes
            computed_modes = my_vec_ops.compute_modes_and_return(mode_nums, 
                [V.InMemoryHandle(vec_mat[:,i]) for i in range(num_vecs)],
                build_coeff_mat, index_from=index_from)
            for mode_index, mode_num in enumerate(mode_nums):
                N.testing.assert_allclose(computed_modes[mode_index], 
                    true_modes[:,mode_num-index_from])
                    
            parallel.sync()

    parallel.sync()


    #@unittest.skip('testing others')
    @unittest.skipIf(parallel.is_distributed(), 'serial only')
    def test_compute_inner_product_mat_types(self):
        class ArrayTextComplexHandle(V.ArrayTextHandle):
            def get(self):
                return (1 + 1j)*V.ArrayTextHandle.get(self)
        
        num_row_vecs = 4
        num_col_vecs = 6
        num_states = 7

        row_vec_path = join(self.test_dir, 'row_vec_%03d.txt')
        col_vec_path = join(self.test_dir, 'col_vec_%03d.txt')
        
        # generate vecs and save to file
        row_vec_mat = N.mat(N.random.random((num_states,
            num_row_vecs)))
        col_vec_mat = N.mat(N.random.random((num_states,
            num_col_vecs)))
        row_vec_paths = []
        col_vec_paths = []
        for vec_index in xrange(num_row_vecs):
            path = row_vec_path % vec_index
            util.save_array_text(row_vec_mat[:,vec_index], path)
            row_vec_paths.append(path)
        for vec_index in xrange(num_col_vecs):
            path = col_vec_path % vec_index
            util.save_array_text(col_vec_mat[:,vec_index], path)
            col_vec_paths.append(path)
    
        # Compute inner product matrix and check type
        for handle, type in [(V.ArrayTextHandle, float), 
            (ArrayTextComplexHandle, complex)]:
            row_vec_handles = [handle(path) for path in row_vec_paths] 
            col_vec_handles = [handle(path) for path in col_vec_paths]
            inner_product_mat = self.my_vec_ops.compute_inner_product_mat(
                row_vec_handles, col_vec_handles)
            symm_inner_product_mat = \
                self.my_vec_ops.compute_symmetric_inner_product_mat(
                    row_vec_handles)
            self.assertEqual(inner_product_mat.dtype, type)
            self.assertEqual(symm_inner_product_mat.dtype, type)



    #@unittest.skip('testing other things')
    def test_compute_inner_product_mats(self):
        """
        Test computation of matrix of inner products in memory-efficient
        chunks, both in parallel (compute_inner_product_mat).
        """ 
        num_row_vecs_list =[1, int(round(self.total_num_vecs_in_mem / 2.)), self.\
            total_num_vecs_in_mem, self.total_num_vecs_in_mem *2,
            parallel.get_num_procs()+1]
        num_col_vecs_list = num_row_vecs_list
        num_states = 6

        row_vec_path = join(self.test_dir, 'row_vec_%03d.txt')
        col_vec_path = join(self.test_dir, 'col_vec_%03d.txt')
        
        for num_row_vecs in num_row_vecs_list:
            for num_col_vecs in num_col_vecs_list:
                # generate vecs and save to file, only do on proc 0
                parallel.sync()
                if parallel.is_rank_zero():
                    row_vec_mat = N.mat(N.random.random((num_states,
                        num_row_vecs)))
                    col_vec_mat = N.mat(N.random.random((num_states,
                        num_col_vecs)))
                    row_vec_handles = []
                    col_vec_handles = []
                    for vec_index in xrange(num_row_vecs):
                        path = row_vec_path % vec_index
                        util.save_array_text(row_vec_mat[:,vec_index],path)
                        row_vec_handles.append(V.ArrayTextHandle(path))
                    for vec_index in xrange(num_col_vecs):
                        path = col_vec_path % vec_index
                        util.save_array_text(col_vec_mat[:,vec_index],path)
                        col_vec_handles.append(V.ArrayTextHandle(path))
                else:
                    row_vec_mat = None
                    col_vec_mat = None
                    row_vec_handles = None
                    col_vec_handles = None
                if parallel.is_distributed():
                    row_vec_mat = parallel.comm.bcast(row_vec_mat, root=0)
                    col_vec_mat = parallel.comm.bcast(col_vec_mat, root=0)
                    row_vec_handles = parallel.comm.bcast(row_vec_handles,
                        root=0)
                    col_vec_handles = parallel.comm.bcast(col_vec_handles, 
                        root=0)

                # If number of rows/cols is 1, check case of passing a handle
                if len(row_vec_handles) == 1:
                    row_vec_handles = row_vec_handles[0]
                if len(col_vec_handles) == 1:
                    col_vec_handles = col_vec_handles[0]

                # True inner product matrix
                product_true = row_vec_mat.T * col_vec_mat
               
                # Test paralleized computation.  
                product_computed = self.my_vec_ops.compute_inner_product_mat(
                    row_vec_handles, col_vec_handles)
                N.testing.assert_allclose(product_computed, product_true)
                        
if __name__=='__main__':
    unittest.main()    

    
    
