#ts to create time series object 
#window for subset of a time series 
#acf for plot of autocorrelation function and values of serial correlations
#diff for differencing a time series
#stl for seasonal-trend-loess smoothing
#loess for trend-loess smoothing without seasonality

v = read.csv("vanc-prec-temp.csv",header=T)
# 1938.01  to 2023.12

totprecip = ts(v$totprecip,start=c(1938,1),frequency=12)
meantemp = ts(v$meantemp,start=c(1938,1),frequency=12)

temp2014to2023 =  window(meantemp,start=c(2014,1),end=c(2023,12))
plot(temp2014to2023,ylab="temp (C)")

ijul = seq(7,nn,12)
precip_jul = ts(v$totprecip[ijul],start=1938,frequency=1)
temp_jul = ts(v$meantemp[ijul],start=1938,frequency=1)

plot(precip_jul, ylab="July precip (mm)")
plot(temp_jul, ylab="July mean temp (C)")

precip_stl = stl(precip2014to2023, s.window=11)
names(precip_stl)
head(precip_stl$time.series)
plot(precip_stl, main="STL applied to precipitation 2014 to 2023")

njul = length(precip_jul)
tt = 1:njul
julprec_loess = loess(precip_jul ~ tt)
matplot(tt+1937,cbind(precip_jul,julprec_loess$fitted),type="l",
  ylab="July precip", main="loess plot",xlab="")

#======================================================================

a = read.csv("CANCPALTT01IXOBSAM.csv",header=T)
cpi = ts(a$CANCPALTT01IXOBSAM, start=c(1992,1), end=c(2025,3), freq=12)
plot(cpi, main="Canada CPI, 2015=100, Seasonally Adj", ylab="CPI")
cpi2010to2024 = window(cpi,start=c(2010,1),end=c(2024,12))
plot(cpi2010to2024, main="Canada CPI, 2010 to 2024", ylab="CPI")
cpi_growth = diff(log(cpi))
head(cpi_growth)
plot(cpi_growth, main="Canada CPI growth, 1992 to 2024",  ylab="CPI growth")
abline(h=0)
cpi_growth2010to2024 = window(cpi_growth, start=c(2010,1),end=c(2024,12))
plot(cpi_growth2010to2024, main="Canada CPI growth, 2010 to 2024", ylab="CPI growth")
abline(h=0)

#======================================================================

g = read.csv("GHGtotal_canada.csv",header=T)
gsub = subset(g,year>=1850)
ghg = ts(asub$totalGHG,start=1850,frequency=1)
ghg1970 = window(ghg,start=1970) 
plot(ghg1970)
tt = 1:length(ghg)
ghg_loess = loess(ghg ~ tt)
tail(ghg_loess$fitted)
ghg_diff = diff(ghg)
ghg1970_diff = window(ghg_diff,start=1970) 
plot(ghg1970_diff)
tem = acf(ghg1970_diff)
round(c(tem$acf),3)

#======================================================================

dc = read.csv("dawson_creek.csv",header=T)
library(lubridate)
yr = lubridate::year(dc$Date)
mo = lubridate::month(dc$Date)
yearmon = 100*yr+mo

mean_discharge_monthly = tapply(dc$discharge,yearmon,mean,na.rm=T)
mean_wlevel_monthly = tapply(dc$wlevel,yearmon,mean,na.rm=T)

max_discharge_monthly = tapply(dc$discharge,yearmon,max,na.rm=T)
max_wlevel_monthly = tapply(dc$wlevel,yearmon,max,na.rm=T)

min_discharge_monthly = tapply(dc$discharge,yearmon,min,na.rm=T)
min_wlevel_monthly = tapply(dc$wlevel,yearmon,min,na.rm=T)

monthly = ts(cbind(mean_discharge_monthly,
   max_discharge_monthly,
   min_discharge_monthly,
   mean_wlevel_monthly,
   max_wlevel_monthly,
   min_wlevel_monthly),
  start=c(2017,1), end=c(2024,12), frequency=12)
summary(monthly)
dawson = ts(dc[,2:3],start=c(2017,1),frequency=365)
plot(dawson)
plot(monthly,main="DawsonCreek, KiskatinawR")

#======================================================================

a = read.csv("CSGBCBRL36to78.csv", skip=3,header=T)
attach(a)
par(mfrow=c(3,3))
plot.ts(CS); title("commercial stock returns")
acf(CS)
acf(abs(CS))
plot.ts(GB); title("gov bond returns")
acf(GB)
acf(abs(GB)) 
plot.ts(CB); title("corp bond returns")
acf(CB)
acf(abs(CB)) 
detach(a)






