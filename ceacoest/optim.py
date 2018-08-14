"""General sparse optimization problem modeling."""


import collections

import attrdict
import numpy as np


class Problem:
    """Sparse optimization problem."""
    
    def __init__(self):
        self.decision_components = collections.OrderedDict()
        """Decision variable component specifications."""
        
        self.nd = 0
        """Total number of problem decision variable elements."""
    
    def register_decision_variable(self, name, shape, broadcast_dims=0):
        component = DecisionComponent(shape, self.nd, broadcast_dims)
        self.decision_components[name] = component
        self.nd += component.size

    def unpack_decision(self, dvec):
        """Unpack the vector of decision variables into its components."""
        dvec = np.asarray(dvec)
        assert d.shape == (self.nd,)

        components = {}
        for name, spec in self.decision_components.items():
            components[name] = spec.extract_from(dvec)
        return components
    
    def pack_decision(self, **components):
        """Pack the decision variable components into the vector."""
        dvec = np.zeros(self.nd)
        for name, spec in self.decision_components.items():
            spec.pack_into(dvec, components[name])
        return dvec

    def register_constraint(self, name, shape, broadcast_dims=0):
        pass


class DecisionComponent:
    """Specificiation of a problem's decision variable component."""
    
    def __init__(self, shape, offset, broadcast_dims=0):
        self.shape = shape
        """The component's ndarray shape."""
        
        self.offset = offset
        """Offset into the decision vector."""
        
        self.size = np.prod(shape, dtype=int)
        """Total number of elements."""
        
        self.slice = slice(offset, offset + self.size)
        """This component's slice in the decision variables vector."""

        base_shape = shape[broadcast_dims:]
        expansion_shape = shape[:broadcast_dims]
        base_size = np.prod(base_shape, dtype=int)
        expansion_size = np.prod(expansion_shape, dtype=int)
        self.expansion_inds = (np.arange(expansion_size)[:, None]*base_size
                               + offset)
        """The offsets for index expansion."""

        self.base_shape = base_shape
        """Shape of the underlying variable, before broadcasting."""
    
    def unpack_from(self, dvec):
        """Extract component from decicion variable vector."""
        return np.asarray(dvec)[self.slice].reshape(self.shape)

    def pack_into(self, dvec, value):
        """Pack component into decicion variable vector."""
        if np.shape(value) != self.shape:
            try:
                value = np.broadcast_to(value, self.shape)
            except ValueError:
                value_shape = np.shape(value)
                msg = "value with shape {} could not be broadcast to {}"
                raise ValueError(msg.format(value_shape, self.shape))
        dvec[self.slice] = np.ravel(value)

    def expand_index(self, indices):
        indices = np.asarray(indices, dtype=int)
        return self.expansion_inds + indices

    def expand_multi_index(self, multi_index):
        indices = np.ravel_multi_index(multi_index, self.base_shape)
        return self.expand_index(indices)
