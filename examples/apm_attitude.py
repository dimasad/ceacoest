"""Attitude reconstruction of an ArduPilot Mega."""


import os
import re

import yaipopt
import numpy as np
import sympy
import sym2num
from numpy import ma
from scipy import io

from ceacoest import kalman, sde, utils


class SymbolicModel(sde.SymbolicModel):
    """Symbolic SDE model."""
    
    var_names = {'t', 'x', 'y', 'q', 'c'}
    """Name of model variables."""
    
    function_names = {'f', 'g', 'h', 'R'}
    """Name of the model functions."""
    
    t = 't'
    """Time variable."""
    
    x = ['ax', 'ay', 'az', 'p', 'q', 'r', 'u', 'v', 'w', 'q0', 'q1', 'q2', 'q3']
    """State vector."""
    
    y = ['ax_meas', 'ay_meas', 'az_meas', 'p_meas', 'q_meas', 'r_meas',
         'magx_meas', 'magy_meas', 'magz_meas']
    """Measurement vector."""
    
    q = ['acc_png', 'omega_png', 'omega_meas_std']
    """Parameter vector."""
    
    c = ['quat_renorm_gain']
    """Constants vector."""
    
    def f(self, t, x, q, c):
        """Drift function."""
        s = self.symbols(t=t, x=x, q=q, c=c)
        renorm = s.quat_renorm_gain*(1 - s.q0**2 - s.q1**2 - s.q2**2 - s.q3**2)
        derivs = dict(
            p=0, q=0, r=0, ax=0, ay=0, az=0,
            q0=-0.5*(s.q1*s.p + s.q2*s.q + s.q3*s.r) + renorm*s.q0,
            q1=-0.5*(-s.q0*s.p - s.q2*s.r + s.q3*s.q) + renorm*s.q1,
            q2=-0.5*(-s.q0*s.q + s.q1*s.r - s.q3*s.p)  + renorm*s.q2,
            q3=-0.5*(-s.q0*s.r - s.q1*s.q + s.q2*s.p)  + renorm*s.q3,
        )
        return self.pack('x', derivs)
    
    def g(self, t, x, q, c):
        """Diffusion matrix."""
        s = self.symbols(t=t, x=x, q=q, c=c)
        g = np.zeros((x.size, 6), object)
        g[[3, 4, 5], [0, 1, 2]] = s.angvel_png
        return g
    
    def h(self, t, x, q, c):
        """Measurement function."""
        s = self.symbols(t=t, x=x, q=q, c=c)
        meas = dict(phi_meas=s.phi, theta_meas=s.theta, psi_meas=s.psi)
        return self.pack('y', meas)
    
    def R(self, q, c):
        """Measurement function."""
        s = self.symbols(q=q, c=c)
        R = np.diag(np.repeat([s.ang_meas_std], 3))**2
        return R


class SymbolicDTModel(SymbolicModel, sde.ItoTaylorAS15DiscretizedModel):
    derivatives = [('df_dx', 'f', 'x'), ('df_dq', 'f', 'q'),
                   ('d2f_dx2', 'df_dx',  'x'), 
                   ('d2f_dx_dq', 'df_dx', 'q'),
                   ('d2f_dq2', 'df_dq',  'q'),
                   ('dQ_dx', 'Q', 'x'), ('dQ_dq', 'Q', 'q'),
                   ('d2Q_dx2', 'dQ_dx',  'x'), 
                   ('d2Q_dx_dq', 'dQ_dx', 'q'),
                   ('d2Q_dq2', 'dQ_dq',  'q'),
                   ('dh_dx', 'h', 'x'), ('dh_dq', 'h', 'q'),
                   ('d2h_dx2', 'dh_dx',  'x'), 
                   ('d2h_dx_dq', 'dh_dx', 'q'),
                   ('d2h_dq2', 'dh_dq',  'q'),
                   ('dR_dq', 'R', 'q'), ('d2R_dq2', 'dR_dq', 'q')]
    """List of the model function derivatives to calculate / generate."""
    
    dt = 'dt'
    """Discretization time step."""

    k = 'k'
    """Discretized sample index."""

    generated_name = "GeneratedDTModel"
    """Name of the generated class."""
    
    meta = 'ceacoest.sde.DiscretizedModel.meta'
    """Generated model metaclass."""
    
    @property
    def imports(self):
        return super().imports + ('import ceacoest.sde',)


sym_model = SymbolicModel()
sym_dt_model = SymbolicDTModel()
printer = sym2num.ScipyPrinter()
GeneratedDTModel = sym2num.class_obj(sym_dt_model, printer)


def load_data():
    module_dir = os.path.dirname(__file__)
    filepath = os.path.join(module_dir, 'data', 'apm.log')
    lines = open(filepath).read().splitlines()

    mag = []
    imu = []
    for line in lines:
        msgid, *fields = re.split(',\s*', line)
        if msgid == 'MAG':
            mag.append([float(field) for field in fields])
        elif msgid == 'IMU':
            imu.append([float(field) for field in fields])
    mag = np.asarray(mag)
    imu = np.asarray(imu)
    #return t, y


def pem(t, y):
    # Instantiate the model
    given = dict(
        ang_meas_std=2.4e-4, angvel_png=3,
    )
    dt = t[1] - t[0]
    q0 = GeneratedDTModel.pack('q', given)
    c = GeneratedDTModel.pack('c', given)
    params = dict(q=q0, c=c, dt=dt)
    sampled = dict(t=t)
    model = GeneratedDTModel(params, sampled)
    x0 = np.zeros(GeneratedDTModel.nx)
    x0[:3] = y[0, :3]
    Px0 = np.diag(np.repeat([1e-3, 1e-3], 3))
    
    def merit(q, new=None):
        mq = model.parametrize(q=q)
        kf = kalman.DTUnscentedKalmanFilter(mq, x0, Px0)
        return kf.pem_merit(y)
    
    def grad(q, new=None):
        mq = model.parametrize(q=q)
        kf = kalman.DTUnscentedKalmanFilter(mq, x0, Px0)
        return kf.pem_gradient(y)
    
    hess_inds = np.tril_indices(model.nq)
    def hess(q, new_q=1, obj_factor=1, lmult=1, new_lmult=1):
        mq = model.parametrize(q=q)
        kf = kalman.DTUnscentedKalmanFilter(mq, x0, Px0)
        return obj_factor * kf.pem_hessian(y)[hess_inds]
    
    q_lb = dict(ang_meas_std=0, angvel_png=0)
    q_ub = dict()
    q_fix = dict(ang_meas_std=2.4e-4)
    q_bounds = [model.pack('q', dict(q_lb, **q_fix), fill=-np.inf),
                model.pack('q', dict(q_ub, **q_fix), fill=np.inf)]
    problem = yaipopt.Problem(q_bounds, merit, grad,
                            hess=hess, hess_inds=hess_inds)
    problem.num_option(b'obj_scaling_factor', -1)
    (qopt, solinfo) = problem.solve(q0)
    
    return problem, qopt, solinfo, model, q0, x0, Px0


if __name__ == '__main__':
    [t, y] = load_data()
    
