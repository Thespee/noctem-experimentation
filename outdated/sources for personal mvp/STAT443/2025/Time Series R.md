# Chapter 1
``` r
library(tseries)
library(zoo)

data <- #
data.ts <- ts(data, start = ,  frequency=)

#plotting:
data.ts.window <- window(data.ts, start =, end = )
plot(data.ts.window, xlab =, ylab =, main =)
#ggplot
autoplot(data.ts.window, xlab, ylab =)

#other
data.annual <- aggregate(data.ts, FUN = mean) 
data.max <- aggregate(data.ts, FUN = max) 
time(data.ts)
# diff() • lag() • lag.plot()
# decompose() # moving average series
# stl() #losess smoothing
```
# Chapter 2
``` r
data <- #
acf() 
rollmean() #moving average at order k
decompose(data, type = "additive | multiplicative") # ts -> trend, seasonal, error using MA(q) process
stl() #losess smoothing

arima.sim() #simulate ARIMA data
ARMAacf() #afc for ARMA process
```