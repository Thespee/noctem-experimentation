ARMA-fc page1
Stat 443. Time Series and Forecasting.
B is the backward shift operator.
Key topics: (a) invertibility for MA polynomial or θ(B) in order
to get h-step forecast for ARMA(p, q),
(b) invertibility for AR polynomial or ϕ(B) in order to get variance
of h-step forecast for ARMA(p, q)
1
ARMA-fc page2
Invertibility
Assume Yt = ˜Yt has been centered to have mean 0.
Consider a stationary ARMA(p, q) time series model
### Yt
=
ϕ1Yt−1 + · · · ϕqYt−p + ϵt + θ1ϵt−1 + · · · + θqϵt−q
ϕ(B)Yt
=
θ(B)ϵt
ϕ(b)
=
1 −ϕ1b −· · · −ϕpbp
θ(b)
=
1 + θ1b + · · · + θqbq
If ϕ(b) is invertible, then (1 −ϕ1b −· · · −ϕpbp)−1 = ϕ−1(b) is a
convergent Taylor series; this is the condition for stationarity.
If θ(b) is invertible, then (1 + θ1b + · · · + θqbq)−1 = θ−1(b) is a
convergent Taylor series; this is the condition for identifiability
(to be explained later via simple cases).
2
ARMA-fc page3
h-step forecasts for ARMA(p, q): ϕ(B) (Yt −µ) = θ(B) ϵt
Invert θ(B) to get:
π(B)(Yt −µ) = θ−1(B)ϕ(B) (Yt −µ) = ϵt, π(b) = 1 −π1b −π2b2 −· · ·
Suppose we have a data series (yt) and estimates ˆµ, (ˆϕi), (ˆθk) after fitting ARMA(p, q) leading
(ˆπi).
Shift indices: substitute forecast values when not yet observed
(Yt −µ)
=
Σ∞
i=1πi(Yt−i −µ) + ϵt
Yn+1
≈
µ + Σn
i=1πi(Yn+1−i −µ) + ϵn+1
ˆyn+1|n
=
ˆµ + Σn
i=1ˆπi(yn+1−i −ˆµ)
Yn+2
≈
µ + Σn+1
i=1 πi(Yn+2−i −µ) + ϵn+2
ˆyn+2|n
=
ˆµ + ˆπ1(ˆyn+1|n −ˆµ) + Σn+1
i=2 ˆπi(yn+2−i −ˆµ)
Yn+3
≈
µ + Σn+2
i=1 πi(Yn+3−i −µ) + ϵn+3
ˆyn+3|n
=
ˆµ + ˆπ1(ˆyn+2|n −ˆµ) + ˆπ2(ˆyn+1|n −ˆµ) + Σn+2
i=3 ˆπi(yn+3−i −ˆµ)
etc.
Special cases of p, q in later slides
3
ARMA-fc page4
Variance of h-step forecasts: ϕ(B) (Yt −µ) = θ(B) ϵt
Invert ϕ(B) to get:
Yt −µ = ϕ−1(B)θ(B)]ϵt = ψ(B)ϵt,
ψ(b) = 1 + ψ1b + ψ2b2 + · · ·
Suppose we have a data series (yt) and estimates ˆµ, (ˆϕj), (ˆθk) after fitting ARMA(p, q) leading
( ˆψi).
Shift indices:
Fn is the information to time n, including ϵn = en, ϵn−1 = en−1, . . . when
“observed”
(Yt −µ)
=
ϵt + Σ∞
i=1ψiϵt−i
Yn+1
≈
µ + ϵn+1 + Σn
i=1ψiϵn+1−i
[Yn+1|Fn]
≈
µ + ϵn+1 + Σn
i=1ψien+1−i
Var (Yn+1|Fn)
=
Var (ϵn+1) = σ2
ϵ
SE(ˆyn+1|n)
=
ˆσϵ
Yn+2
≈
µ + ϵn+2 + ψ1ϵn+1 + Σn
i=2ψiϵn+2−i
[Yn+2|Fn]
≈
µ + ϵn+2 + ψ1ϵn+1 + Σn
i=2ψien+2−i
Var (Yn+2|Fn)
=
Var (ϵn+2 + ψ1ϵn+1) = (1 + ψ2
1)σ2
ϵ
SE(ˆyn+2|n)
=
(1 + ˆψ2
1)1/2ˆσϵ
Yn+3
≈
µ + ϵn+3 + ψ1ϵn+2 + ψ2ϵn+1 + Σn
i=3ψiϵn+3−i
[Yn+3|Fn]
≈
µ + ϵn+3 + ψ1ϵn+2 + ψ2ϵn+1 + Σn
i=3ψien+3−i
Var (Yn+3|Fn)
=
Var (ϵn+3 + ψ1ϵn+2 + ψ2ϵn+1) = (1 + ψ2
1 + ψ2
2)σ2
ϵ
SE(ˆyn+3|n)
=
(1 + ˆψ2
1 + ˆψ2
2)1/2ˆσϵ
SE(ˆyn+h|n)
=
(1 + Σh−1
j=1 ˆψ2
j )1/2ˆσϵ,
increasing in h = 2, . . .
To check with R output in some cases.
4
ARMA-fc page5
Forecasting for stationary AR(2). Training set of length n.
Let ˜Yt = Yt −µ. ˜Yi = ϕ1˜Yi−1 + ϕ2˜Yi−2 + ϵi
˜Yt
=
ϕ1˜Yt−1 + ϕ2˜Yt−2 + ϵt
=
ϕ1(ϕ1˜Yt−2 + ϕ2˜Yt−3 + ϵt−1) + ϕ2˜Yt−2 + ϵt
=
(ϕ2
1 + ϕ2)˜Yt−2 + ϕ1ϕ2˜Yt−3 + ϕ1ϵt−1 + ϵt
˜Yn+1
=
ϕ1˜Yn + ϕ2˜Yn−1 + ϵn+1
ˆyn+1|n
=
ˆyn+1 = ˆµ + ˆϕ1(yn −ˆµ) + ˆϕ2(yn−1 −ˆµ)
˜Yn+2
=
(ϕ2
1 + ϕ2)˜Yn + ϕ1ϕ2˜Yn−1 + ϕ1ϵn+1 + ϵn+2
ˆyn+2|n
=
ˆµ + (ˆϕ2
1 + ˆϕ2)(yn −ˆµ) + ˆϕ1ˆϕ2(yn−1 −ˆµ)
=
ˆyn+2 = ˆµ + ˆϕ1(ˆyn+1 −ˆµ) + ˆϕ2(yn −ˆµ)
ˆyn+3|n
=
ˆyn+3 = ˆµ + ˆϕ1(ˆyn+2 −ˆµ) + ˆϕ2(ˆyn+1 −ˆµ)
etc.
Iterate: use estimated ˆyt if Yt is not observed at time n.
Var (Yn+1|Fn)
=
Var (Yn+1|observations to time n) = Var (ϵn+1) = σ2
ϵ
Var (Yn+2|Fn)
=
ϕ2
1Var (ϵn+1) + Var (ϵn+2) = (ϕ2
1 + 1)σ2
ϵ
SE(ˆyn+1|n)
=
ˆσϵ
SE(ˆyn+2|n)
=
(ˆϕ2
1 + 1)1/2ˆσϵ
Relate to π(b) = ϕ(b) and ψ(b) series.
5
ARMA-fc page6
Variance of forecast for AR(2): use the ψ(B) series.
ϕ(b)
=
1 −ϕ1b −ϕ2b2
ψ(b)
=
ϕ−1(b) because θ(b) = 1
1
=
ψ(b)ϕ(b) = (1 + ψ1b + ψ2b2 + ψ3b3 + · · ·)(1 −ϕ1b −ϕ2b2)
Coefficients for b1, b2, b3, . . . should be 0 to solve for ψ1, ψ2, . . ..
b1
:
−ϕ1 + ψ1 = 0 ⇒ψ1 = ϕ1
b2
:
−ϕ2 −ψ1ϕ1 + ψ2 = 0 ⇒ψ2 = ϕ2 + ψ1ϕ1
b3
:
−ψ1ϕ2 −ψ1ϕ1 + ψ3 = 0 ⇒ψ3 = ψ1ϕ2 + ψ2ϕ1
bk
:
−ψk−2ϕ2 −ψk−1ϕ1 + ψk = 0 ⇒ψk = ψk−2ϕ2 + ψk−1ϕ1,
k ≥3
Compare with the ARMAtoMA() function in R.
6
ARMA-fc page7
ARMAtoMA(ar = numeric(), ma = numeric(), lag.max)
This function can produce the ψk coefficients in the MA(∞)
representation.
# phi1 = 0.4; phi2 = 0.2
psiv = rep(0,6)
psiv[1] = phi1; psiv[2] = phi2+psiv[1]*phi1
for(k in 3:6) psiv[k] = psiv[k-2]*phi2 + psiv[k-1]*phi1
psiv2 = ARMAtoMA(ar=c(phi1,phi2), lag.max=6)
print(psiv)
# [1] 0.400000 0.360000 0.224000 0.161600 0.109440 0.076096
print(psiv2)
# [1] 0.400000 0.360000 0.224000 0.161600 0.109440 0.076096
phi1 = 0.4; phi2 = 0.2; theta1 = 0.5
psivec = ARMAtoMA(ar=c(phi1,phi2), ma=c(theta1), lag.max=6)
print(psivec)
# [1] 0.900000 0.560000 0.404000 0.273600 0.190240 0.130816
7
ARMA-fc page8
Check output of unempl-tsmodel.Rmd
dlny_ar2ml = arima(ytrain[,’dlny’],order=c(2,0,0),method="ML")
#>
ar1
ar2
intercept
#>
0.3532 0.1597
-0.0051
#> s.e. 0.1106 0.1120
0.0068
sigma^2 estimated as 0.0009023
phi1 = dlny_ar2ml$coef[1]; phi2 = dlny_ar2ml$coef[2]; mu = dlny_ar2ml$coef[3]
predobj = predict(dlny_ar2ml, n.ahead=4, se.fit=T)
#>
year
Qtr1
Qtr2
Qtr3
Qtr4
#> $pred
2007 -0.005639112 -0.007769369 -0.006112258 -0.005867239
#> $se
2007
0.03003797
0.03185616
0.03298193
0.03331674
sigma = sigmahat=sqrt(dlny_ar2ml$sigma2)= 0.03004,
phi1=phi1hat= 0.3532, phi2=phi2hat= 0.1597,
mu=muhat= -0.0051
dlny_ntrain = ytrain[ntrain,’dlny’]
= -0.02072608
dlny_nminus1 = ytrain[ntrain-1,’dlny’] = 0.02597554
## 1-step forecast: dlnyhat(n+1) = dlnyhat_nplus1 =
-0.005639
=
mu + phi1*(dlny_ntrain-mu) + phi2*(dlny_nminus1-mu) =
-0.0051 +0.3532*(-0.0207261+0.0051) + 0.1597*(0.0259755+0.0051)
2-step forecast: dlnyhat(n+2) = dlnyhat_nplus2 = -0.007769369 =
mu + phi1*(dlnyhat_nplus1-mu) + phi2*(dlny_ntrain-mu) =
-0.0051 +0.3532*(-0.005639 +0.0051) + 0.1597*(-0.0207261+0.0051)
SEdlnyhat(n+1) = sigma = 0.03004
SEdlnyhat(n+2) = sigma*sqrt(1+phi1^2) = 0.03186 # psi1=phi1 for AR(2)
etc
Exercise: confirm the third and fourth SE in the predict output; see preceding slide
8
ARMA-fc page9
Variance of forecast for AR(1)
˜Yn+1
=
ϕ˜Yn + ϵn+1
˜Yn+2
=
ϕ˜Yn+1 + ϵn+2 = ϕ2˜Yn + ϕϵn+1 + ϵn+2
˜Yn+3
=
ϕ˜Yn+2 + ϵn+3 = ϕ3˜Yn + ϕ2ϵn+1 + ϕϵn+2 + ϵn+3
˜Yn+h
=
ϕh˜Yn + Σh
j=1ϕh−jϵn+j
Var (˜Yn+h|Yn = yn, . . . , Y1 = y1)
=
σ2
ϵ Σh
j=1ϕ2(h−j)
SE(ˆyn+h|n)
=
ˆσϵ

Σh
j=1ˆϕ2(h−j)1/2
Confirm with AR(1) model for furnace data in webwork exercise
9
ARMA-fc page10
ARMA(1,1): Deriving π(b) and ψ(b)
Yt = ϕYt−1 + ϵt + θϵt−1, −1 < ϕ < 1, −1 ≤θ ≤1.
(1 −ϕB)Yt = (1 + θB)ϵt, what happens if ϕ = −θ?
Deducing ψ(b)
• ψ(b) = (1 −ϕb)−1(1 + θb) = (1 + ψ1b + ψ2b2 + · · ·)
• (1 + ψ1b + ψ2b2 + · · ·)(1 −ϕb) = (1 + θb)
• Match powers of b
• b1: −ϕ + ψ1 = θ ⇒ψ1 = θ + ϕ
• b2: −ψ1ϕ + ψ2 = 0 ⇒ψ2 = ϕψ1
• bk: −ψk−1ϕ + ψk = 0 ⇒ψk = ϕψk−1 = ϕk−1ψ1, k ≥2.
Deducing π(b)
• π(b) = (1 + θb)−1(1 −ϕb) = (1 −π1b −π2b2 −· · ·)
• (1 −π1b −π2b2 −· · ·)(1 + θb) = (1 −ϕb)
• Match powers of b
• b1: θ −π1 = −ϕ ⇒π1 = θ + ϕ
• b2: −π1θ −π2 = 0 ⇒π2 = −θπ1
• bk: −πk−1θ −πk = 0 ⇒πk = −θπk−1 = (−θ)k−1π1, k ≥2.
Use similar steps for ARMA(2,1)
10
ARMA-fc page11
Take-home message
1. When using statistical method for the first time in a software,
check that you can match each outputted value to theory.
2.
ARMA(p, q) with q ≥1:
1-step forecast ˆyt+1|t is a linear
function of yt, . . . , y1 but can be truncated to the most recent m
previous observations where the coefficients are not negligible.
11
