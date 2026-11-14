* FO4 two ways: explicit transistor widths, and subcircuit parameters. Both must agree.
simulator lang=spice
.lib "MODELS/sky130.lib.spice" tt
.param u=1e-6
.subckt inv a y vdd vss wn=0.42 wp=0.84
xp y a vdd vdd pfet_01v8 l=0.15u w='wp*u'
xn y a vss vss nfet_01v8 l=0.15u w='wn*u'
.ends
vdd vdd 0 1.8
vin in 0 pulse(0 1.8 200p 30p 30p 1n 2n)
* Explicit widths
xp0 a0 in vdd vdd pfet_01v8 l=0.15u w=0.84u
xn0 a0 in 0 0 nfet_01v8 l=0.15u w=0.42u
xpa b0 a0 vdd vdd pfet_01v8 l=0.15u w=3.36u
xna b0 a0 0 0 nfet_01v8 l=0.15u w=1.68u
xpb c0 b0 vdd vdd pfet_01v8 l=0.15u w=13.44u
xnb c0 b0 0 0 nfet_01v8 l=0.15u w=6.72u
xpc d0 c0 vdd vdd pfet_01v8 l=0.15u w=53.76u
xnc d0 c0 0 0 nfet_01v8 l=0.15u w=26.88u
* Subcircuit with parameters
x0 in a vdd 0 inv
x1 a b vdd 0 inv wn=1.68 wp=3.36
x2 b c vdd 0 inv wn=6.72 wp=13.44
x3 c d vdd 0 inv wn=26.88 wp=53.76
* One inverter of each size into 20 fF
xs in ys vdd 0 inv
cs ys 0 20f
xl in yl vdd 0 inv wn=1.68 wp=3.36
cl yl 0 20f
.tran 0.5p 3n
.measure tran exp_fall trig v(a0) val=0.9 rise=1 targ v(b0) val=0.9 fall=1
.measure tran exp_rise trig v(a0) val=0.9 fall=1 targ v(b0) val=0.9 rise=1
.measure tran sub_fall trig v(a) val=0.9 rise=1 targ v(b) val=0.9 fall=1
.measure tran sub_rise trig v(a) val=0.9 fall=1 targ v(b) val=0.9 rise=1
.measure tran small_20f trig v(in) val=0.9 rise=1 targ v(ys) val=0.9 fall=1
.measure tran large_20f trig v(in) val=0.9 rise=1 targ v(yl) val=0.9 fall=1
.end
