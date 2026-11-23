"""예제 모터 철손 −24%의 역추론: 모델에 빠진 항이 어느 정도여야 JMAG 751 W가 되고, 그 크기가 물리적으로 그럴듯한가.

방법: FEA 점 B 파형(fine_d2, 가장 조밀한 표본)을 성분별 푸리에 분해해 히스테리시스 · 고전 와전류 손실을 따로 합산하고,
부족분(JMAG 751 W − 모델)을 Bertotti의 이상(excess) 손실 P_exc = k_exc·(f·B)^1.5 한 항으로 채우는 데 필요한 k_exc를 구한다.
이것은 보정이 아니라 가설 점검이다(모델·엔진에는 넣지 않는다). 판정 기준: 구한 k_exc가 50 Hz, 1.5 T에서 만드는 이상 손실이 카탈로그 W15/50의 몇 %인가.
Bertotti, IEEE Trans. Magn. 24(1), 621 (1988)이 정의한 세 분리 항(히스테리시스 + 고전 와전류 + 이상). 면적 5% 부족 보정(비교용)도 같이 본다.
실행: python notebooks/17_example_motor_iron_inference.py
"""
import sys, math
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.steel import load_steel
import importlib.util
spec=importlib.util.spec_from_file_location("n15", ROOT / "notebooks" / "15_example_motor_iron_loss.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
st=load_steel("35JN230")
print("k_h",st.k_h,"alpha",st.alpha,"k_e",st.k_e)
d=np.load(ROOT / "data" / "fea" / "example_motor_iron_probes_fine_d2.npz")
pos=np.radians(d["positions_deg"]); B=d["B_xy_T"].astype(float); ns=int(d["n_stator"])
reg,sa,ra=d["stator_region"],d["stator_area_m2"],d["rotor_area_m2"]
kg=m.STACK*m.LAM_FILL*st.density_kg_m3
def split(bx,by,w,mult):
    h=e=x=0.0
    for j in range(bx.shape[1]):
        for comp in (bx[:,j],by[:,j]):
            c=np.fft.rfft(comp)/len(comp)*2
            for k in range(1,len(c)):
                a=abs(c[k]); f=k*m.F1
                h+=st.k_h*f*a**st.alpha*w[j]*kg*mult
                e+=st.k_e*(f*a)**2*w[j]*kg*mult
                x+=(f*a)**1.5*w[j]*kg*mult
    return h,e,x
H=E=X=0
for code in (0,1,2):
    mk=reg==code
    h,e,x=split(B[:,:ns,0][:,mk],B[:,:ns,1][:,mk],sa[mk],4.0); H+=h;E+=e;X+=x
rb=(B[:,ns:,0]+1j*B[:,ns:,1])*np.exp(-1j*pos)[:,None]
h,e,x=split(rb.real,rb.imag,ra,8.0);H+=h;E+=e;X+=x
print(f"hyst {H:.0f} W, classical eddy {E:.0f} W, total {H+E:.0f}; sum (fB)^1.5 weighted {X:.1f}")
for tgt in (751.48, 751.48/1.05):
    need=tgt-(H+E)
    print(f"target {tgt:.0f}: extra {need:.0f} W -> k_exc = {need/X:.2e} W/kg/(Hz T)^1.5 ; eddy multiplier alone {1+need/E:.2f} ; hysteresis multiplier alone {1+need/H:.2f}")
# excess at 50Hz,1.5T for implied k_exc
for tgt in (751.48,751.48/1.05):
    kx=(tgt-(H+E))/X
    print(f"  50 Hz, 1.5 T의 이상 손실 {kx*(50*1.5)**1.5:.2f} W/kg = 카탈로그 W15/50 2.10 W/kg의 {100*kx*(50*1.5)**1.5/2.10:.0f} %")
