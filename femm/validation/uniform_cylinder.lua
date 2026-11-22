-- 해석해 검증 2: 균일장 B0 속의 무한 선형 원통(mu_r). 영구자석이 없는 순수 선형 문제.
-- 해석해(Rfar -> 무한): 내부 Bx = 2 mu_r / (mu_r + 1) * B0
-- 바깥 경계는 A = B0 * y (Prescribed A, A2 = B0)로 균일장을 만든다.
B0 = 0.1
MUR = 10
R = 0.01
Rfar = 0.3
MESH_IRON = 0.0002
MESH_AIR = 0.002

newdocument(0)
mi_probdef(0, "meters", "planar", 1e-10, 1, 30)
mi_addmaterial("Fe", MUR, MUR, 0, 0, 0, 0, 0, 1, 0, 0, 0)
mi_addmaterial("Air", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)
mi_addboundprop("U", 0, 0, B0, 0, 0, 0, 0, 0, 0)
mi_addnode(R, 0) mi_addnode(-R, 0)
mi_addarc(R, 0, -R, 0, 180, 1) mi_addarc(-R, 0, R, 0, 180, 1)
mi_addnode(Rfar, 0) mi_addnode(-Rfar, 0)
mi_addarc(Rfar, 0, -Rfar, 0, 180, 2) mi_addarc(-Rfar, 0, Rfar, 0, 180, 2)
mi_selectarcsegment(0, Rfar) mi_selectarcsegment(0, -Rfar)
mi_setarcsegmentprop(2, "U", 0, 0) mi_clearselected()
mi_addblocklabel(0, 0) mi_selectlabel(0, 0)
mi_setblockprop("Fe", 0, MESH_IRON, 0, 0, 0, 0) mi_clearselected()
mi_addblocklabel(Rfar / 2, 0) mi_selectlabel(Rfar / 2, 0)
mi_setblockprop("Air", 0, MESH_AIR, 0, 0, 0, 0) mi_clearselected()
mi_saveas("uniform_cylinder.fem")
mi_analyze()
mi_loadsolution()
a, bx, by = mo_getpointvalues(0.002, 0.003)
print(format("RESULT Bx=%.8f By=%.8f", bx, by))
