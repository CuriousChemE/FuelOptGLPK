# FuelOptGLPK
Cloud-based Pyomo application with GLPK solver

This is an interactive optimization application, optimizing fuel delivery to over 200 stations in Florida.  Model parameters are fictitious.

The application uses Bokeh for interacting with the user and for displaying a scrollable interactive map with the results (using Open Route Service), with Bokeh callback to collect inputs from user, formulate the optimization model and constraints, solve the optimization problem and report the results.   

The application is built on the <a href="https://github.com/Pyomo/pyomo/blob/master/LICENSE.txt">Pyomo</a> open-source optimization platform, and hosted in the cloud on heroku.

Since it took me a while to figure out how to host a Pyomo app on the cloud, I'll share how that was ultimately implemented.  The biggest challenge was installing the solver code (open-source GLPK) which Pyomo uses to solve the optimization problem, since GLPK is not a python library (hence cannot be installed via the requirements.txt file).  Instead, the GLPK solver was insatleld via the use of an "Aptfile" and heroku's buildpacks for python applications and for installs as specified in an Aptfile. 

On your local machine, cd into the folder where the application lies (same structure as in this github), then follow the steps below to create the heroku app, specify python libraries as listed in requirements.txt and binaries as listed in Aptfile, then push the application to heroku:

```
$ git init
$ git add .
$ git commit -m "first commit"
$ heroku create fueloptg
$ heroku buildpacks:set heroku/python
$ heroku buildpacks:add --index 1 heroku-community/apt
$ git push heroku master
```

