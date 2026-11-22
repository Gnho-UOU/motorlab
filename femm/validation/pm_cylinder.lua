-- 해석해 검증 1: 균일 자화된 무한 원통(planar, mu_r = 1)의 내부 자속밀도.
-- 해석해: Bx = (Br/2) * (1 - (R/Rfar)^2)  (바깥 경계 A = 0, Rfar가 크면 Br/2)
-- FEMM과 xfemm(femmcli) 양쪽에서 같은 스크립트가 돌아야 한다. run_checks.py가 아래 파라미터 줄을 바꿔 실행한다.
Br = 1.2
R = 0.01
Rfar = 0.3
MESH_MAGNET = 0.0002
MESH_AIR = 0.002

mu0 = 4 * 3.14159265358979e-7
newdocument(0)
mi_probdef(0, "meters", "planar", 1e-10, 1, 30)
mi_addmaterial("PM", 1, 1, Br / mu0, 0, 0, 0, 0, 1, 0, 0, 0)
mi_addmaterial("Air", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)
mi_addboundprop("A0", 0, 0, 0, 0, 0, 0, 0, 0, 0)
mi_addnode(R, 0) mi_addnode(-R, 0)
mi_addarc(R, 0, -R, 0, 180, 1) mi_addarc(-R, 0, R, 0, 180, 1)
mi_addnode(Rfar, 0) mi_addnode(-Rfar, 0)
mi_addarc(Rfar, 0, -Rfar, 0, 180, 2) mi_addarc(-Rfar, 0, Rfar, 0, 180, 2)
mi_selectarcsegment(0, Rfar) mi_selectarcsegment(0, -Rfar)
mi_setarcsegmentprop(2, "A0", 0, 0) mi_clearselected()
mi_addblocklabel(0, 0) mi_selectlabel(0, 0)
mi_setblockprop("PM", 0, MESH_MAGNET, 0, 0, 0, 0) mi_clearselected()
mi_addblocklabel(Rfar / 2, 0) mi_selectlabel(Rfar / 2, 0)
mi_setblockprop("Air", 0, MESH_AIR, 0, 0, 0, 0) mi_clearselected()
mi_saveas("pm_cylinder.fem")
mi_analyze()
mi_loadsolution()
a, bx, by = mo_getpointvalues(0, 0.002)
print(format("RESULT Bx=%.8f By=%.8f", bx, by))
