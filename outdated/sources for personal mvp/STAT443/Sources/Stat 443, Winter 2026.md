
      Stat 443, Time Series and Forecasting, Winter 2026 term

Instructor office hour: Wed 3:00-4:00pm by zoom (meeting ID on canvas
page), or by appointment,

------------------------------------------------------------------------


        Overview

Notation and big picture <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/
Notes/stat443-notation-bigpicture.pdf> for Stat 443, and main learning
objectives.

Study habits <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/
howtostudy_stat443.html> helpful for Stat 443 (and other courses).

Roadmap for Stat 443:

 1. Forecasting rules and interpretations, comparison of forecasting
    rules; motivation from data examples
 2. From forecasting rules to time series models assuming additive
    innovations
 3. Dependence properties of Gaussian time series models (additions Jan
    28): the following properties will take several lectures to cover.
      * AR(p) time series models are stationary only if the phi
        parameters satisfy some constraints
      * MA(q) time series models are always stationary but parameter
        estimates are restricted to satisfy some constraints
      * ARMA(p,q) time series models are stationary only if the phi
        parameters satisfy some constraints
      * ARIMA(p,1,q) time series models are not stationary; if a time
        series (Y_t ) of random variables requires differencing to be
        stationary, then the sequence (Y_t ) is not stationary.
      * One cannot prove that a data time series (y_t ) is stationary or
        non-stationary (likewise one cannot prove that a sample comes
        from a normal/Gaussian distribution).
      * Diagnostics such as the variogram and acf can suggest whether
        the data series (y_t ) can be considered stationary for the
        purpose of short-term forecasting, or whether the data series
        should be differenced to be considered stationary for the
        purpose of short-term forecasting. 
 4. Derivations of forecast intervals and applications in data examples
    and case studies 

------------------------------------------------------------------------


        Labs and Homework

Labs: Summary for labs that require canvas upload <https://
uglab.stat.ubc.ca/~h.joe/Stat443-2026/labs.html>. Note that labs 5 and 6
consist of exercises to do and submit in the lab hour.

Homework assignments: Summary for exercises (Webwork) and assigments
(canvas upload) <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/
homework.html> (new Webwork Feb 4)

In class iClickers: documents with answers and feedback <https://
uglab.stat.ubc.ca/~h.joe/Stat443-2026/iclickers.html> (by date)

------------------------------------------------------------------------


        Topics by lecture

  * (Jan 6) Introduction <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/
    intro443-2026.html> and outline for Stat 443.
    Introductory slides with time series examples, plots and notation
    <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/Slides/stat443-ts-
    examples.pdf>, also textbook H&A, Chapter 2, Sections 6.1, 6.6
    Goal is to come up with a variety of forecasting rules for different
    types of time series behavior.
    timeseries-Rfunctions.r <https://uglab.stat.ubc.ca/~h.joe/
    Stat443-2026/Code/timeseries-Rfunctions.r> examples of R functions
    used in the data sets cited in the above-listed document.

  * (Jan 8) Forecasting rules and comparisons for some data sets
    <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/Slides/stat443-
    forecast-rules.pdf>; also H&A , Sections 3.1, 3.4.
    forecast-rules-examples.pdf <https://uglab.stat.ubc.ca/~h.joe/
    Stat443-2026/Code/forecast-rules-examples.pdf> and forecast-rules-
    examples.Rmd <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/Code/
    forecast-rules-examples.Rmd> (latter is the Rmarkdown code file that
    produce the tables in the slides. These two files updated on Jan 13
    after class, corrections on the final level and slope in the
    training set.
    Forecasting rules and comparisons for some data sets <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Slides/stat443-forecast-rules-
    corrections.pdf> (with corrections Jan 13)

  * (Jan 13) Stochastic models (random walk, autoregressive) associated
    with forecasting rules; Simple exponential smoothing (H&A, Section
    7.1).
    From forecast rules to stochastic model <https://uglab.stat.ubc.ca/
    ~h.joe/Stat443-2026/Slides/stat443-fcrule-model.pdf>.
    For an example of simple exponential smoothing in R, see forecast-
    rules-examples.pdf <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/
    Code/forecast-rules-examples.pdf>

  * (Jan 15, 20) Holt linear exponential smoothing <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Slides/stat443-
    linearexpsmo.pdf> with trend (time-varying slope). (H&A, Section 7.2).
    See the Notes section below for a summary of all of the Holt-Winters
    exponential smoothing rules.
    Exponential smoothing rules with trend and seasonality. (H&A,
    Section 7.3).
    Winters seasonal exponential smoothing <https://uglab.stat.ubc.ca/
    ~h.joe/Stat443-2026/Slides/stat443-seasonal-expsmo.pdf>.
    Example that includes prediction interval (predict method for
    HoltWinters) YVR-monthlytemp.pdf <https://uglab.stat.ubc.ca/~h.joe/
    Stat443-2026/Code/YVR-monthlytemp.pdf> and YVR-monthlytemp.Rmd
    <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/Code/YVR-
    monthlytemp.Rmd>
    Revision (after class) with 273 added to temperature for degree
    Kelvin: YVR-monthlytemp-revised-multrule.pdf <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Code/YVR-monthlytemp-revised-
    multrule.pdf> and YVR-monthlytemp-revised-multrule.Rmd <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Code/YVR-monthlytemp-revised-
    multrule.Rmd>; parameters estimates (alpha, beta, gamma) for
    multiplicative rule are now close to additive rule, and holdout set
    rmse of the two are the same, but 12-step ahead forecast interval
    for the multiplicative rule is based on an unstable formula.

  * (Jan 20,22) Time series in two variables; cross-correlation function
    (ccf in R) and other visualizations. Forecasting y based on another
    variable x; forecasting rules y_t+1|t using more information than
    previous values y_1 ,...,y_t . (Textbook H&A Sections 5.4, 5.6.)
    Forecasting with regression on other variables <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Slides/stat443-fc-reg.pdf>.
    Partial case study: unemployment rate and GDP (gross domestic
    product): unemploy-gdp.pdf <https://uglab.stat.ubc.ca/~h.joe/
    Stat443-2026/Code/unemploy-gdp.pdf> and unemploy-gdp.Rmd <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Code/unemploy-gdp.Rmd>

  * (Jan 22,27) stat443-projects.pdf <https://uglab.stat.ubc.ca/~h.joe/
    Stat443-2026/Slides/stat443-projects.pdf> Information about
    requirements for the team-based term project. Project proposal to be
    submitted via canvas tentatively by Feb 12, deadline for submission
    of project report is April 10.

  * (beginning Jan 27) Some questions/exercises (some in red colour in
    slides) will be asked via iClickers in class; these count as marks
    towards the homework total.
    iClickers Join Code : https://join.iclicker.com/XLTZ
    iClickers Student app : XLTZ to register

  * (Jan 27, 29) Stationary time series models, autoregressive, moving
    average (more precisely, moving weighted sum). (Textbook H&A
    Sections 8.1-8.7.)
    Introduction to ARMA <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/
    Slides/stat443-arma.pdf>.

  * (Jan 29) Examples of plots for time series: variogram, acf, pacf,
    smoothed periodogram: variogram-examples.pdf <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Code/variogram-examples.pdf>
    and variogram-examples.Rmd <https://uglab.stat.ubc.ca/~h.joe/
    Stat443-2026/Code/variogram-examples.Rmd>.
    If a data time series (y_t ) is approximately stationary, then two
    estimates Ghat_k and Hhat_k of the variogram should be similar.
    If a data time series (y_t ) is approximately stationary after
    differencing, Ghat_k correctly estimates the variogram and Hhat_k
    does not estimate the variogram, so Ghat_k and Hhat_k can be quite
    different.

  * Announcements Jan 27, Jan 29
    Possible move to DMP 310 beginning Tue Feb 3 (waiting for reasons).
    DMP = Hugh Dempster Pavilion, 6245 Agronomy, south end of campus.
    Go south on Main Mall, turn left at Agronomy, walk to the alley. or
    Go south on Main Mall, cut through Kaiser building, turn right after
    reaching the alley, building on left side when Agronomy is reached.
    No response yet from Scheduling Services, so watch for information
    on canvas and the course web site by Monday Feb 2, on whether there
    is a room change.
    If you have a class before or after Stat 443 that is in the north of
    the campus and 15 minutes away from DMP 310, please email the
    instructor.

  * (Feb 3, CHEM B250) (Textbook H&A Sections 8.1-8.7.)
    Examples of data applications using R functions for fitting time
    series models, including arima function.
    unemploy-tsmodels.pdf <https://uglab.stat.ubc.ca/~h.joe/
    Stat443-2026/Code/unemploy-tsmodels.pdf> and unemploy-tsmodels.Rmd
    <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/Code/unemploy-
    tsmodels.Rmd>.
    Theory AR(p) part1 <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/
    Slides/stat443-ar-part1.pdf>.

  * (Feb 5, CHEM B250; Feb 10 DMP310) h-step forecasts and coresponding
    SEs for stationary ARMA ARMA-forecast <https://uglab.stat.ubc.ca/
    ~h.joe/Stat443-2026/Slides/stat443-arma-fc.pdf>.
    ARMA for diff(woolyrnq), a data set in library(forecast): woolyarn-
    arma.pdf <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/Code/
    woolyarn-arma.pdf> and woolyarn-arma.Rmd <https://uglab.stat.ubc.ca/
    ~h.joe/Stat443-2026/Code/woolyarn-arma.Rmd>.

  * (Feb 10 and rest of term in DMP 310) AR time series and conditions
    for stationarity. Dependence properties. More theory for ARMA. 

------------------------------------------------------------------------


        Data sets used in the lectures, examples, labs and homework

  * Vancouver monthly temperature and total precipitation (mm) <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Data/vanc-prec-temp.csv>
    1938-01 to 2023-12.
  * Canadian monthly CPI (consumer price index, growth rate in CPI is a
    proxy for inflation) in 2015 dollars <https://uglab.stat.ubc.ca/
    ~h.joe/Stat443-2026/Data/CANCPALTT01IXOBSAM.csv>, 1992-01 to
    2025-03, seasonally adjusted
  * CS=commercial stocks, GB=government bonds, CB=corporate bonds,
    RL=riskfree asset <https://uglab.stat.ubc.ca/~h.joe/Stat443-2026/
    Data/CSGBCBRL36to78.csv> 1936-Q1 to 1978-Q4. from Grauer and
    Hakansson (1982). Finance Analysts Journal, vol 38, pp 39-53.
  * Total GHG by year in Canada <https://uglab.stat.ubc.ca/~h.joe/
    Stat443-2026/Data/GHGtotal_canada.csv> 1850-2023. (add units)
  * Daily discharge and water level at a river in Dawson Creek <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Data/dawson_creek.csv>
    2017-01-01 to 2024-12-31 (add units)
  * Quarterly GDP and unemployment rate in Canada <https://
    uglab.stat.ubc.ca/~h.joe/Stat443-2026/Data/gdp-unemploy-FRED.csv>
    (seasonally adjusted) 1961-Q1 to 2025-Q1. 

------------------------------------------------------------------------


        Team project due February 11

Review for possible topics <https://uglab.stat.ubc.ca/~h.joe/
Stat443-2026/Slides/stat443_projects.pdf>

To be submitted on canvas by February 11: a pdf file/document.
The file name should have form Surname1Surname2Surname3Surname4-
stat443proposal.pdf (no spaces and commas in file name). The pdf file
should be uploaded from just one team member.
The document should be about 2 pages in length, with the research
question, the variable you are forecasting or modelling, explanatory
variables if relevant, multiple time series if relevant, and data
sources. Also include the members of the team.
If you already have some preliminary data to check feasibility, you may
want to do some plots to check that your data are adequate but this need
not be included in the proposal.

Unless you are using data from a previous kaggle data competition, you
likely will need to find data on the internet for your research
question. The team project involves more than analyzing a data set from
a textbook.

Learning outcomes for this project:

  * (a) Get some ideas about efforts needed to get data for a research
    question. Getting the data and creating the appropriate explanatory
    variables could be more time consuming than fitting models, so
    teamwork can combine the required efforts. So you need a project
    that does not take too much time to acquire/wrangle the data.
  * (b) Get some practice in writing a report.
  * (c) Get some experience in project teamwork.
  * (d) Become more interested in the course material because you need
    it for a project that is of personal interest. 

Items (a), (b) and (c) lead to useful skills for post-graduation work.

The required format for the final report will be posted later.

------------------------------------------------------------------------


      Reference Notes

This section will have notes on topics that are not well-covered by
textbooks on time series and hence can be considered as supplementary
material. Not all material in these reference notes will be covered in
lectures. They are useful if you would like to pursue a future MSc degree.

  * Exponential smoothing methods <https://uglab.stat.ubc.ca/~h.joe/
    Stat443-2026/Notes/stat443-expsmo.pdf> see also wikipedia article on
    exponential smoothing <https://en.wikipedia.org/wiki/
    Exponential_smoothing>. Books on time series now tend to start with
    autoregressive moving average (ARMA) and autoregressive integrated
    moving average (ARIMA), but exponential smoothing methods provide
    more intuitive forecasting rules and lead to ARIMA models. 

------------------------------------------------------------------------
