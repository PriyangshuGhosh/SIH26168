"""Small NumPy reference for Member 3's 8-state EKF contract."""
from dataclasses import dataclass
import math
import numpy as np

@dataclass
class Config:
    gnss_nis_threshold: float = 5.991
    speed_nis_threshold: float = 3.841
    nhc_nis_threshold: float = 3.841
    nhc_variance: float = 0.04
    max_measurement_age_s: float = 2.0
    max_measurement_lead_s: float = 0.10
    accel_noise_std: float = 0.5
    gyro_noise_std: float = 0.05
    accel_bias_rw_std: float = 0.02
    gyro_bias_rw_std: float = 0.002
    degraded_process_scale: float = 4.0

class EKFReference:
    """State [north,east,vx,vy,yaw,bax,bay,bgz]; SI units and radians."""
    def __init__(self, config=None): self.cfg=config or Config(); self.reset()
    def reset(self):
        self.x=np.zeros(8); self.P=np.diag([25.,25.,4.,4.,math.pi**2,.25,.25,.25]); self.t=None; self.ref=None
    @staticmethod
    def _yaw(a): return (a+math.pi)%(2*math.pi)-math.pi
    def _scalar(self,innovation,H,R,threshold):
        S=float(H@self.P@H.T+R); nis=innovation*innovation/S
        if not np.isfinite(S) or S<=1e-9 or not np.isfinite(nis) or nis>threshold:return False
        K=self.P@H.T/S; A=np.eye(8)-K@H; self.x+=K[:,0]*innovation; self.P=A@self.P@A.T+K*R@K.T; self.P=(self.P+self.P.T)*.5; self.x[4]=self._yaw(self.x[4]); return np.isfinite(self.x).all()
    def predict(self,t,ax,ay,gz,fully_aligned=True):
        if not np.isfinite([t,ax,ay,gz]).all(): return False
        if self.t is None:self.t=float(t);return True
        raw=t-self.t
        if raw<=0:return False
        if raw>1:self.P[2,2]+=self.cfg.accel_noise_std**2*max(raw,1);self.P[3,3]+=self.cfg.accel_noise_std**2*max(raw,1);self.t=float(t);return True
        dt=min(raw,.1); yaw=self.x[4];c,s=math.cos(yaw),math.sin(yaw);vx,vy=self.x[2:4]
        ax-=self.x[5];ay-=self.x[6];gz-=self.x[7];self.x[0]+=(vx*c-vy*s)*dt;self.x[1]+=(vx*s+vy*c)*dt;self.x[2]+=ax*dt;self.x[3]+=ay*dt;self.x[4]=self._yaw(yaw+gz*dt)
        F=np.eye(8);F[0,2]=c*dt;F[0,3]=-s*dt;F[1,2]=s*dt;F[1,3]=c*dt;F[0,4]=(-vx*s-vy*c)*dt;F[1,4]=(vx*c-vy*s)*dt;F[2,5]=-dt;F[3,6]=-dt;F[4,7]=-dt
        scale=1 if fully_aligned else self.cfg.degraded_process_scale;aq=scale*self.cfg.accel_noise_std**2;gq=scale*self.cfg.gyro_noise_std**2;Q=np.zeros((8,8));Q[0,0]=Q[1,1]=.25*aq*dt**3;Q[2,2]=Q[3,3]=aq*dt;Q[4,4]=gq*dt;Q[5,5]=Q[6,6]=self.cfg.accel_bias_rw_std**2*dt;Q[7,7]=self.cfg.gyro_bias_rw_std**2*dt
        self.P=F@self.P@F.T+Q
        if fully_aligned:
            H=np.zeros((1,8));H[0,3]=1;self._scalar(-self.x[3],H,self.cfg.nhc_variance,self.cfg.nhc_nis_threshold)
        self.t=float(t);return np.isfinite(self.x).all() and np.isfinite(self.P).all()
    def update_speed(self,t,velocity,variance):
        if self.t is not None and (t>self.t+self.cfg.max_measurement_lead_s or t<self.t-self.cfg.max_measurement_age_s):return False
        if not np.isfinite([t,velocity,variance]).all() or velocity<0 or velocity>100 or variance<=0:return False
        H=np.zeros((1,8));H[0,2]=1;return self._scalar(velocity-self.x[2],H,max(variance,1e-4),self.cfg.speed_nis_threshold)
