"""POD class"""
import numpy as N

from vectorspace import VectorSpace
import util
import parallel as parallel_mod
parallel = parallel_mod.parallel_default_instance

class POD(object):
    """Proper Orthogonal Decomposition.
    
    Args:
        inner_product: Function to find inner product of two vector objects.
    
    Kwargs:
        
        put_mat: Function to put a matrix out of modred
      	
      	get_mat: Function to get a matrix into modred
      	
        verbosity: 0 prints almost nothing, 1 prints progress and warnings
        
        max_vecs_per_node: max number of vectors in memory per node.
        
    Computes orthonormal POD modes from vecs.  
    It uses :py:class:`vectorspace.VectorSpace` for low level functions.

    Usage::
      
      myPOD = POD(my_inner_product)
      myPOD.compute_decomp(vec_handles)
      myPOD.compute_modes(range(10), mode_handles)
    
    See also :mod:`vectors`.
    """
    def __init__(self, inner_product, 
        get_mat=util.load_array_text, put_mat=util.save_array_text, 
        max_vecs_per_node=None, verbosity=0):
        """Constructor """
        self.vec_space = VectorSpace(inner_product=inner_product, 
            max_vecs_per_node=max_vecs_per_node, 
            verbosity=verbosity)
        self.get_mat = get_mat
        self.put_mat = put_mat
        self.verbosity = verbosity
        self.eigen_vecs = None
        self.eigen_vals = None
        self.correlation_mat = None
        self.vec_handles = None
        self.vecs = None

     
    def sanity_check(self, test_vec_handle):
        """Check user-supplied vector handle.
        
        Args:
            test_vec_handle: a vector handle.
        
        See :py:meth:`vectorspace.VectorSpace.sanity_check`.
        """
        self.vec_space.sanity_check(test_vec_handle)

    def sanity_check_in_memory(self, test_vec):
        """Check user-supplied vector object.
        
        Args:
            test_vec: a vector.
        
        See :py:meth:`vectorspace.VectorSpace.sanity_check_in_memory`.
        """
        self.vec_space.sanity_check_in_memory(test_vec)

     
    def get_decomp(self, eigen_vecs_source, eigen_vals_source):
        """Gets the decomposition matrices from sources (memory or file)"""
        if self.get_mat is None:
            raise util.UndefinedError('Must specify a get_mat function')
        if parallel.is_rank_zero():
            self.eigen_vecs = self.get_mat(eigen_vecs_source)
            self.eigen_vals = N.squeeze(N.array(
                self.get_mat(eigen_vals_source)))
        else:
            self.eigen_vecs = None
            self.eigen_vals = None
        if parallel.is_distributed():
            self.eigen_vecs = parallel.comm.bcast(self.eigen_vecs, root=0)
            self.eigen_vals = parallel.comm.bcast(self.eigen_vals, root=0)
        
        
    def put_decomp(self, eigen_vecs_dest, eigen_vals_dest):
        """Put the decomposition matrices to file or memory."""
        self.put_eigen_vecs(eigen_vecs_dest)
        self.put_eigen_vals(eigen_vals_dest)
        
    def put_eigen_vecs(self, dest):
        """Put singular vectors, U (==V)"""
        if self.put_mat is None and parallel.is_rank_zero():
            raise util.UndefinedError("put_mat is undefined")
            
        if parallel.is_rank_zero():
            self.put_mat(self.eigen_vecs, dest)
        parallel.barrier()

    def put_eigen_vals(self, dest):
        """Put singular values, E"""
        if self.put_mat is None and parallel.is_rank_zero():
            raise util.UndefinedError("put_mat is undefined")
            
        if parallel.is_rank_zero():
            self.put_mat(self.eigen_vals, dest)
        parallel.barrier()

    def put_correlation_mat(self, correlation_mat_dest):
        """Put correlation matrix"""
        if self.put_mat is None and parallel.is_rank_zero():
            raise util.UndefinedError("put_mat is undefined")
        if parallel.is_rank_zero():
            self.put_mat(self.correlation_mat, correlation_mat_dest)
        parallel.barrier()


    def compute_decomp(self, vec_handles):
        """Computes correlation mat X*X, then the eigen decomp of this matrix.
        
        Args:
            vec_handles: list of handles for vecs
            
        Returns:
            eigen_vecs: matrix of singular vectors (U, ==V, in UEV*=H)
        
            eigen_vals: 1D array of singular values (E in UEV*=H) 
        """
        self.vec_handles = vec_handles
        self.correlation_mat = self.vec_space.\
            compute_symmetric_inner_product_mat(self.vec_handles)
        #self.correlation_mat = self.vec_space.\
        #    compute_inner_product_mat(self.vec_handles, self.vec_handles)
        self.compute_eigen_decomp()        
        return self.eigen_vecs, self.eigen_vals
       
    def compute_decomp_in_memory(self, vecs):
        """Same as ``compute_decomp`` but takes vecs instead of handles"""
        self.vecs = vecs
        self.correlation_mat = self.vec_space.\
            compute_symmetric_inner_product_mat_in_memory(self.vecs)
        #self.correlation_mat = self.vec_space.\
        #    compute_inner_product_mat(self.vec_handles, self.vec_handles)
        self.compute_eigen_decomp()
        return self.eigen_vecs, self.eigen_vals    
        
    def compute_eigen_decomp(self):
        """Compute eigen decmop, UE=correlation_mat*U"""
        if parallel.is_rank_zero():
            self.eigen_vals, self.eigen_vecs = util.eigh(self.correlation_mat)
        else:
            self.eigen_vecs = None
            self.eigen_vals = None
        if parallel.is_distributed():
            self.eigen_vecs = parallel.comm.bcast(self.eigen_vecs, root=0)
            self.eigen_vals = parallel.comm.bcast(self.eigen_vals, root=0)
            
            
            
            
    def _compute_build_coeff_mat(self):
        """Helper for ``compute_modes`` and ``compute_modes_and_return``."""
        #self.eigen_vecs, self.eigen_vals must exist or an UndefinedError.
        if self.eigen_vecs is None:
            raise util.UndefinedError('Must define self.eigen_vecs')
        if self.eigen_vals is None:
            raise util.UndefinedError('Must define self.eigen_vals')
        build_coeff_mat = N.dot(self.eigen_vecs, N.diag(self.eigen_vals**-0.5))
        return build_coeff_mat
    
    def compute_modes(self, mode_nums, mode_handles,
        vec_handles=None, index_from=0):
        """Computes the modes and calls ``put`` on them.
        
        Args:
            mode_nums: Mode numbers to compute. 
              Examples are ``range(10)`` or ``[3, 1, 6, 8]``. 
              
            mode_handles: list of handles for modes
            
        Kwargs:
            vec_handles: list of handles for vectors. 
	            Optional if already given when calling ``compute_decomp``.

            index_from: Index modes starting from 0, 1, or other.
        """
        if vec_handles is not None:
            self.vec_handles = util.make_list(vec_handles)
        build_coeff_mat = self._compute_build_coeff_mat()
        self.vec_space.compute_modes(mode_nums, mode_handles,
             self.vec_handles, build_coeff_mat, index_from=index_from)
    
    def compute_modes_in_memory(self, mode_nums, vecs=None, index_from=0):
        """Computes the modes and calls ``put`` on them.
        
        Args:
            mode_nums: Mode numbers to compute. 
              Examples are ``range(10)`` or ``[3, 1, 6, 8]``. 
              
        Kwargs:
            vecs: list of handles for vectors. 
	            Optional if already given when calling ``compute_decomp``.

            index_from: Index modes starting from 0, 1, or other.
        
        Returns:
            modes: list of all modes with numbers in ``mode_nums``.
        
        See :py:meth:`compute_modes`.
        In parallel, each processor returns all modes.
        """
        if vecs is not None:
            self.vecs = util.make_list(vecs)
        build_coeff_mat = self._compute_build_coeff_mat()
        return self.vec_space.compute_modes_in_memory(mode_nums,
             self.vecs, build_coeff_mat, index_from=index_from)
    
