* Sanity check of the sky130 models: saturation current and gate charge of 1 um transistors.
simulator lang=spice
.lib "MODELS/sky130.lib.spice" tt
vdd vdd 0 1.8
* Saturation current, Vgs = Vds = 1.8 V
vdn dn 0 1.8
vin_n dn2 0 0
xn1 dn vdd 0 0 nfet_01v8 l=0.15u w=1u
xp1 0 0 vdd vdd pfet_01v8 l=0.15u w=1u
* Gate charge: ramp the gates 0 -> 1.8 V, source/drain/bulk tied to their rails
vgn gn 0 pwl(0 0 1n 1.8)
xn2 0 gn 0 0 nfet_01v8 l=0.15u w=1u
vgp gp 0 pwl(0 1.8 1n 0)
xp2 vdd gp vdd vdd pfet_01v8 l=0.15u w=1u
.tran 1p 1.2n
.measure tran idn find i(vdn) at=1.1n
.measure tran idp find i(vdd) at=1.1n
.measure tran qn integ i(vgn) from=0 to=1n
.measure tran qp integ i(vgp) from=0 to=1n
.end
