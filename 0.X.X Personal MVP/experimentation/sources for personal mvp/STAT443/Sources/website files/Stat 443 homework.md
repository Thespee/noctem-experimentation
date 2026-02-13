
      Stat 443 homework

Webwork problem sets consist of exercises to assess minimal
understanding of course material.

Assignments with submissions via canvas assess deeper understanding with
open-ended questions.

------------------------------------------------------------------------


        Webwork

After the first exercise set, the due date will be shortly after the
relevant lecture.

  * exerciseset01: open 2026-01-12; due date 2026-01-21 (Wednesday).
    Inputting answers to 3 significant digits or 3 decimal places should
    be adequate.
     1. Problem 1: compute acf in R; e.g. acf(y,lag.max=5,plot=F)$acf
     2. Problem 2: there is a small training set and a smaller holdout
        set; compute rmse of 1-step forecasts with 3 forecast rules --
        persistence, average in training set, regression on the most
        recent previous. 
    For both problems, you will get randomly generated data.

  * exerciseset02: open 2026-01-16; due date 2026-01-23 (Friday).
    Inputting answers to 3 significant digits or 3 decimal places should
    be adequate.
     1. Problem 1: compute Var(Y[t+1]) in AR(1) stochastic model.
     2. Problem 2: coefficients in stochastic model for Holt damped
        trend (slope) exponential smoothing: input the coefficients for
        a specific case of alpha, beta, phi. See below for the
        associated assignment01. 
    For both problems, you will get randomly generated parameters.

  * exerciseset03: one topic is using the arima function in R. Open
    2026-02-04: due date 2026-01-12 (Thursday).
     1. Problem 1: fitting AR models and getting holdout set rmse's for
        data set furnace.csv <https://uglab.stat.ubc.ca/~h.joe/
        Stat443-2026/Data/furnace.csv> (from book by Bisgaard and
        Kulahci "Time Series Analysis and Forecasting by Example").
     2. Problem 2: autocorrelation function for MA(1) model. 

------------------------------------------------------------------------


        Assignments (canvas upload required)

For assignments, if you are working in a group, only one person needs to
upload, but members of all group names should be in the uploaded pdf
file. Upload can be pdf file converted from MSWord (or equivalent with
Googledocs, OpenOffice) or LaTeX, or a scan of something handwritten.

  * assignment01: See slide page 7 in stat443-linearexposmo.pdf. Use the
    technique in slide page 6 and derive the stochastic model associated
    with Holt damped trend (slope) exponential smoothing. As a check if
    your derivation is correct, you should answer Problem 2, in Webwork
    exerciseset02 correctly. 

