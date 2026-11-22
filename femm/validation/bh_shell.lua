-- 해석해 검증 3: 비선형 BH. 중심의 전류선 I와 강판 원통(r1 < r < r2).
-- 대칭성 때문에 H(r) = I / (2 pi r) 이고 B(r) = f(H)가 정확한 해석해다 (포화 영역 포함).
-- BH 곡선(테스트용 합성): B = 2 tanh(H / 3000) + mu0 H
IAMP = 300
MESH_STEEL = 0.001

mu0 = 4 * 3.14159265358979e-7
pi = 3.14159265358979
function bh(h) return 2.0 * tanh(h / 3000) + mu0 * h end
a = 0.005 r1 = 0.02 r2 = 0.04 Rfar = 0.3

newdocument(0)
mi_probdef(0, "meters", "planar", 1e-10, 1, 30)
mi_addmaterial("Cu", 1, 1, 0, IAMP / (pi * a * a) / 1e6, 0, 0, 0, 1, 0, 0, 0)
mi_addmaterial("Air", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)
mi_addmaterial("Steel", 1, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0)
mi_addbhpoint("Steel", 0, 0)
h = 5.0
while h < 3e6 do
  mi_addbhpoint("Steel", bh(h), h)
  h = h * 1.25
end
mi_addboundprop("A0", 0, 0, 0, 0, 0, 0, 0, 0, 0)
function circle(rad, seg)
  mi_addnode(rad, 0) mi_addnode(-rad, 0)
  mi_addarc(rad, 0, -rad, 0, 180, seg) mi_addarc(-rad, 0, rad, 0, 180, seg)
end
circle(a, 2) circle(r1, 2) circle(r2, 2) circle(Rfar, 3)
mi_selectarcsegment(0, Rfar) mi_selectarcsegment(0, -Rfar)
mi_setarcsegmentprop(3, "A0", 0, 0) mi_clearselected()
mi_addblocklabel(0, 0) mi_selectlabel(0, 0) mi_setblockprop("Cu", 0, 0.001, 0, 0, 0, 0) mi_clearselected()
mi_addblocklabel(0.012, 0) mi_selectlabel(0.012, 0) mi_setblockprop("Air", 0, 0.002, 0, 0, 0, 0) mi_clearselected()
mi_addblocklabel(0.03, 0.001) mi_selectlabel(0.03, 0.001)
mi_setblockprop("Steel", 0, MESH_STEEL, 0, 0, 0, 0) mi_clearselected()
mi_addblocklabel(0.15, 0) mi_selectlabel(0.15, 0) mi_setblockprop("Air", 0, 0.01, 0, 0, 0, 0) mi_clearselected()
mi_saveas("bh_shell.fem")
mi_analyze()
mi_loadsolution()
for i = 1, 3 do
  r = 0.022 + (i - 1) * 0.008
  aa, bx, by = mo_getpointvalues(r, 0)
  print(format("RESULT r=%.4f B=%.8f expected=%.8f", r, sqrt(bx * bx + by * by), bh(IAMP / (2 * pi * r))))
end
