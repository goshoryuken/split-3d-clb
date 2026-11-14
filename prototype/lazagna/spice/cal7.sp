* ASAP7 model check: current and gate charge of one-fin RVT transistors at 0.7 V, and FO4.
simulator lang=spice
.include "MODELS/7nm_TT_160803.pm"
.temp 25
vdd vdd 0 0.7
* Saturation current, Vgs = Vds = 0.7 V
vdn dn 0 0.7
mn1 dn vdd 0 0 nmos_rvt l=21n nfin=1
mp1 0 0 vdd vdd pmos_rvt l=21n nfin=1
* Gate charge: ramp the gates, source/drain/bulk tied to their rails, 10 fins each
vgn gn 0 pwl(0 0 1n 0.7)
mn2 0 gn 0 0 nmos_rvt l=21n nfin=10
vgp gp 0 pwl(0 0.7 1n 0)
mp2 vdd gp vdd vdd pmos_rvt l=21n nfin=10
* FO4 chain, inverter size 1 = 1 fin n + PF fins p
.param pf=1
.subckt inv a y vdd vss sz=1
mp y a vdd vdd pmos_rvt l=21n nfin='sz*pf'
mn y a vss vss nmos_rvt l=21n nfin='sz'
.ends
vin in 0 pulse(0 0.7 200p 10p 10p 1n 2n)
x0 in a vdd 0 inv
x1 a b vdd 0 inv sz=4
x2 b c vdd 0 inv sz=16
x3 c d vdd 0 inv sz=64
.tran 0.1p 2.5n
.measure tran idn find i(vdn) at=1.1n
.measure tran idp find i(vdd) at=1.1n
.measure tran qn integ i(vgn) from=0 to=1n
.measure tran qp integ i(vgp) from=0 to=1n
.measure tran fo4_fall trig v(a) val=0.35 rise=1 targ v(b) val=0.35 fall=1
.measure tran fo4_rise trig v(a) val=0.35 fall=1 targ v(b) val=0.35 rise=1
.end
