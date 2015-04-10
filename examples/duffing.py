'''Test various modules using a Duffing oscillator SDE model.'''


import numpy as np
import sympy
import sym2num
from numpy import ma
from scipy import stats


from qwfilter import kalman, sde


class SymbolicDuffing(sde.EulerDiscretizedModel):
    '''Symbolic Duffing oscillator model.'''

    var_names = ['t', 'x', 'y', 'q', 'c', 't_next']
    '''Name of model variables.'''
    
    function_names = ['f', 'g', 'h', 'R']
    '''Name of the model functions.'''

    derivatives = [('dfd_dx', 'fd', 'x'), ('dfd_dq', 'fd', 'q'),
                   ('dQd_dx', 'Qd', 'x'), ('dQd_dq', 'Qd', 'q'),
                   ('dh_dx', 'h', 'x'), ('dh_dq', 'h', 'q'),
                   ('dR_dq', 'R', 'q'),]
    '''List of the model function derivatives to calculate / generate.'''
    
    t = 't'
    '''Time variable.'''

    k = 'k'
    '''Discretized time index.'''
    
    td = 'Td'
    '''Discretization period.'''
    
    x = ['x', 'v']
    '''State vector.'''
    
    y = ['x_meas']
    '''Measurement vector.'''
    
    q = ['alpha', 'beta', 'delta', 'g1', 'x_meas_std']
    '''Unknown parameter vector.'''
    
    c = ['gamma', 'omega']
    '''Constants vector.'''
    
    def f(self, t, x, q, c):
        '''Drift function.'''
        s = self.symbols(t=t, x=x, q=q, c=c)
        f1 = s.v
        f2 = (-s.delta * s.v - s.beta * s.x - s.alpha * s.x ** 3  +
              s.gamma * sympy.cos(s.t * s.omega))
        return [f1, f2]
    
    def g(self, t, x, q, c):
        '''Diffusion matrix.'''
        s = self.symbols(t=t, x=x, q=q, c=c)
        return [[0], [s.g1]]
    
    def h(self, t, x, q, c):
        '''Measurement function.'''
        s = self.symbols(t=t, x=x, q=q, c=c)
        return [s.x]
    
    def R(self, q, c):
        '''Measurement function.'''
        s = self.symbols(q=q, c=c)
        return [[s.x_meas_std ** 2]]


GeneratedDuffing = sym2num.class_obj(
    SymbolicDuffing(), sym2num.ScipyPrinter(),
    name='GeneratedDuffing', 
    meta=sym2num.ParametrizedModel.meta
)


def sim():
    given = dict(
        alpha=1, beta=-1, delta=0.2, gamma=0.3, omega=1,
        g1=0.1, x_meas_std=0.1
    )
    q = GeneratedDuffing.pack('q', given)
    c = GeneratedDuffing.pack('c', given)
    model = GeneratedDuffing(dict(q=q, c=c))
    
    t = np.arange(0, 20, 0.1)
    N = t.size
    x = np.zeros((N, model.nx))
    x[0] = [1, 0]
    for k, tk in enumerate(t[:-1]):
        td = (tk, t[k + 1])
        wk = np.random.randn(model.nw)
        x[k + 1] = model.fd(td, x[k])
        x[k + 1] += model.gd(td, x[k]).dot(wk)

    R = model.R()
    v = np.random.multivariate_normal(np.zeros(model.ny), R, N)
    y = ma.asarray(model.h(t, x) + v)
    y[::2] = ma.masked
    
    return model, t, x, y


def filter(model, t, x, y):
    filtopts = dict(save_history='filter', calculate_gradients=True)
    x0_mean = [1.2, 0.2]
    x0_cov = np.diag([0.1, 0.1])
    filt = kalman.DTUnscentedKalmanFilter(model, x0_mean, x0_cov, **filtopts)
    filt.filter(t, y)
    