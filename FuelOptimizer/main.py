import pandas as pd
import pyomo.environ as pyomo
import pyomo.gdp as gdp
from pyomo.opt import SolverStatus, TerminationCondition
from bokeh.models import Button, Slider, RangeSlider,Label,Div,HoverTool, Div
from bokeh.plotting import ColumnDataSource, figure, output_file, show
from bokeh.layouts import column, row, layout
from bokeh.io import output_file, show, curdoc
from bokeh.tile_providers import get_provider, Vendors #CARTODBPOSITRON
from bokeh.models.widgets import DataTable, TableColumn, NumberFormatter
# from bokeh.models import SingleIntervalTicker, NumeralTickFormatter,RadioButtonGroup

# import data for (one-way) station-terminal times, distances, station demands, cost of supply at each terminal
# import capacity constraint at each terminal and geolocation data for stations and terminals
# time and distance data for all terminal-station pairs computed with openrouteservice.org

pathname='FuelOptimizer/data/distancetablemercFL.xlsx'
# pathnamemap='figures/FLmap.png'
dfdistance = pd.read_excel(pathname, 'distancetable',header=0, index_col=0)
dftime = pd.read_excel(pathname, 'timetable',header=0, index_col=0)
dfdemands = pd.read_excel(pathname, 'demands',header=0, index_col=0)
# put dfdemands in array form (same demands from each terminal...sum of terminal usage forced to 1 in constraints)
dfdemandsarray=pd.concat([dfdemands]*dfdistance.shape[1],axis=1,ignore_index=True)
# read in consolidated terminal data
dftd = pd.read_excel(pathname, 'terminaldata',header=0, index_col=0)
# read in geographic station data
DFstations = pd.read_excel(pathname, 'stationlist',header=0, index_col=0)

# get map tile
tile_provider = get_provider(Vendors.CARTODBPOSITRON_RETINA)
    
# read in model parameters
DFparameters = pd.read_excel(pathname, 'parameters',header=0, index_col=0)
TruckCapacity=DFparameters.parameter.TruckCapacity #gallons per tanker truck
CostPerMile=DFparameters.parameter.CostPerMile
CostTruckMonth=DFparameters.parameter.CostTruckMonth
CostPerHour=DFparameters.parameter.CostPerHour
TruckHours=DFparameters.parameter.TruckHours #available truck hours in period (30 days, 720=24/7 operation)

#draw initial map, with all stations gray (as read in from input file)
cdsInitStations=ColumnDataSource(DFstations)
cdsTerminals=ColumnDataSource(dftd)
x_range,y_range=([-9350837,-8794239], [2875744,3632749]) #bounding box for Florida
plot=figure(x_range=x_range,y_range=y_range,x_axis_type='mercator',y_axis_type='mercator',plot_width=500,tools='pan,wheel_zoom,reset',sizing_mode='fixed',active_scroll='wheel_zoom')
plot.add_tile(tile_provider)
# seed with color
PlotStation=plot.circle('Xmerc','Ymerc',source=cdsInitStations,fill_color='color',size=5,fill_alpha=0.8,line_width=0.5)
plot.add_tools(HoverTool(renderers=[PlotStation],tooltips=[('Station','@StationAddress'),('Supplier','@TName'),('cpg','@cpg')]))
PlotTerminal=plot.diamond('Xmerc','Ymerc',source=cdsTerminals,fill_color='color',size=15,fill_alpha=0.8,line_width=0.5)
plot.add_tools(HoverTool(renderers=[PlotTerminal],tooltips=[('Terminal','@terminalname'),('Trucks','@Trucks'),('Demand (kgal/mo)','@Demand'),('Stations Supplied','@Stations'),('Trips','@Trips')]))

#create page title
divheader=Div(text='<H2 style="white-space: nowrap">Florida Gasoline Optimizer - adjust inputs and click Optimize</H2>')
#create placeholder for objfn value
objtext='objective not calculated'
divright = Div(text=objtext, style={'font-size': '150%', 'color': 'red'})
#create Optimize button
OptButton = Button(label='Optimize',sizing_mode='fixed')
#create copyright script (add link to license file)
divcopy=Div(text='Copyright (c) 2020 Francis X. Kelly under License')
#set up output table
columns = [TableColumn(field="terminalname", title="Terminal"),TableColumn(field="Trucks", title="Trucks",formatter=NumberFormatter(format='0.00')), TableColumn(field="Stations", title="Stations supplied",formatter=NumberFormatter(format='0')),TableColumn(field="Trips", title="# of trips",formatter=NumberFormatter(format='0')),TableColumn(field="Demand", title="Demand kgal/mo",formatter=NumberFormatter(format='0'))]
OutputTable=DataTable(source=cdsTerminals, columns=columns, width=600, height=600,index_position=None,sizing_mode='fixed')

CapacitySliderHeader='<b>Terminal min/max capacity, gal/mo</b>'
divCSH = Div(text=CapacitySliderHeader, style={'font-size': '100%', 'color': 'black'},sizing_mode='fixed')
sliders=[]
for rowi in dftd.itertuples():
    CapacitySlider = RangeSlider(start=0, end=10000000, value=(rowi.Tmin,rowi.capacity), step=100000, title=rowi.terminalname, bar_color=rowi.color,format='0,0',sizing_mode='fixed')
    sliders.append(CapacitySlider)

CostSliderHeader='<b>Supply premium(+)/discount(-), cpg</b>'
divCostSH = Div(text=CostSliderHeader, style={'font-size': '100%', 'color': 'black'},sizing_mode='fixed')
sliderSCost=[]
for rowj in dftd.itertuples():
    SCostSlider = Slider(start=-2, end=2, value=(rowj.supplycost), step=0.5, title=rowj.terminalname, bar_color=rowj.color,sizing_mode='fixed')
    sliderSCost.append(SCostSlider)

# define function for callback on optimize function, which will update the cdsStation and cdsTerminals variables to refresh the plot, and the OutputTable

# do sequential callbacks - one to put up status indicator, next to do the actual calculations
def opt_click():
    divright.text='<i>calculating...</i>'
    curdoc().add_next_tick_callback(opt_click_work)
def opt_click_work():
    #retrieve values from sliders for capacity and Tmin
    for slidi in range(0,len(sliders)):
        dftd.loc[slidi, ('Tmin')]=sliders[slidi].value[0]
        dftd.loc[slidi, ('capacity')]=sliders[slidi].value[1]
    #retrieve values from sliders for supply costs   
    for slidj in range(0,len(sliderSCost)):
        dftd.loc[slidj, ('supplycost')]=sliderSCost[slidj].value/100 # read in cents, convert to dollars
       
    # pre-compute cost data per station-terminal pair (in dataframe matrix algebra)
    TruckLoads=dfdemandsarray/TruckCapacity
    MileageCost=2*dfdistance*CostPerMile*TruckLoads #round-trip
    #TripHours=TruckLoads*((2*dftime)+ExtraTime)/60
    TripHours=TruckLoads*((2*dftime)+dftd.extratime)/60
    TimeCost=TripHours*CostPerHour
    TruckCost=CostTruckMonth*TripHours/TruckHours
    SupplyCost=dfdemandsarray*dftd.supplycost
    TotalCost=SupplyCost+TruckCost+TimeCost+MileageCost
    #convert TotalCost into Indexed Dictionary variable for passing to pyomo as the objective function
    N = list(TotalCost.index.map(int))
    M = list(TotalCost.columns.map(int))
    dTotalCost = {(n, m):TotalCost.at[n,m] for n in N for m in M}

    #Create pyomo model
    model = pyomo.ConcreteModel()
    N = list(TotalCost.index.map(int))
    M = list(TotalCost.columns.map(int))
    model.Stations = range(1+max(N))
    model.Terminals = range(1+max(M))
    #decision variables - forcing to binary makes all supply to station from a single terminal
    model.x = pyomo.Var(model.Stations, model.Terminals, within=pyomo.Binary) ## to set as continuous, bounds=(0.0,1.0)
    #objective function - minimize total cost to supply/deliver to each station
    model.obj=pyomo.Objective(expr=sum(dTotalCost[n,m]*model.x[n,m] for n in model.Stations for m in model.Terminals))
    #constraints
    model.constraints = pyomo.ConstraintList()
    # force terminal selection for each station to sum to 1 (forces demand to be met)
    for n in model.Stations:
        model.constraints.add(sum( model.x[n,m] for m in model.Terminals) == 1.0 )
    # establish volume constraints at each terminal
    for m in model.Terminals: 
        model.constraints.add(expr=sum( model.x[n,m]*dfdemands.demands[n] for n in model.Stations) <= dftd.capacity[m]) 
    # force EITHER >=minimum or zero offtakefrom each terminal, using pyomo.gdp Disjunction
    # need a disjunction pair for each terminal where min or zero offtake imposed
    model.d=gdp.Disjunction(model.Terminals, rule = lambda n,m:[sum(model.x[n,m]*dfdemands.demands[n] for n in model.Stations)==0,sum(model.x[n,m]*dfdemands.demands[n] for n in model.Stations)>=dftd.Tmin[m]])
    # transform the model using "big M" methodology so that it can be solved with open-source cbc solver
    xfrm=pyomo.TransformationFactory('gdp.bigm')
    xfrm.apply_to(model)    
    #run model
    solver = pyomo.SolverFactory('glpk')
    solver.options['tmlim'] = 45  # stop solver if not converged in 45 seconds
    results = solver.solve(model)
    # check for convergence
    if results.solver.termination_condition == TerminationCondition.infeasible: #means over-constrained
        objtext='infeasible'
        divright.text=objtext
        cdsInitStations.data['color']=cdsInitStations.data['failcolor']
        return()
    if results.solver.termination_condition == TerminationCondition.feasible:  # means that solver timed out
        objtext='failed to converge'
        divright.text=objtext
        cdsInitStations.data['color']=cdsInitStations.data['failcolor']
        return()
    objtext='Total cost = '+'${:,.0f}'.format((results['Problem'][0])['Lower bound']) + '/month'
    divright.text=objtext
    # retrieve model solution
    DFTerminalAssignment = pd.DataFrame()
    for n in N:
        for m in M:

            DFTerminalAssignment.at[n,m] = int(model.x[(n,m)].value) # don't convert to integer if x is continuous

    DFtn=DFTerminalAssignment.idxmax(axis=1).to_frame(name="color")
    DFtn=DFtn['color'].map(dftd.set_index('terminalnumber')['color'])
    cpg=(100*(TotalCost*DFTerminalAssignment).sum(axis=1) /dfdemands['demands']).round(2).to_frame(name="cpg")
    #StationMap=DFstations.merge(DFtn,left_index=True, right_index=True)
    DFstations.color=DFtn
    StationMap=DFstations.merge(cpg,left_index=True, right_index=True) 
    dftname=DFTerminalAssignment.idxmax(axis=1).to_frame(name="TName")
    dftname=dftname['TName'].map(dftd.set_index('terminalnumber')['terminalname'])
    StationMap=StationMap.merge(dftname,left_index=True, right_index=True) 
    cdsInitStations.data=StationMap
    
    # summarize data by terminal
    OutputTerminalTable=pd.DataFrame() # dftd.terminalname.to_frame(name="terminalname")
    OptTruckReq=TripHours*DFTerminalAssignment/TruckHours
    OutputTerminalTable['Trucks']=OptTruckReq.sum(axis=0)
    OutputTerminalTable['Demand']=(dfdemandsarray*DFTerminalAssignment).sum(axis=0)/1000
    OutputTerminalTable['Stations']=DFTerminalAssignment.sum(axis=0)
    OutputTerminalTable['Trips']=(TruckLoads*DFTerminalAssignment).sum(axis=0)
    tmap=dftd.merge(OutputTerminalTable,left_index=True, right_index=True)
    cdsTerminals.data=tmap
    columns = [TableColumn(field="terminalname", title="Terminal"),TableColumn(field="Trucks", title="Trucks"), TableColumn(field="Stations", title="Stations supplied"),TableColumn(field="Trips", title="# of trips"),TableColumn(field="Demand", title="Demand kgal/mo")]
    OutputTable=DataTable(source=cdsTerminals, columns=columns, width=600, height=600,index_position=None,sizing_mode='fixed')
    

#obt=Div(text=objtext)  
#grid=layout([OptButton,divright],[plot,,sliders,OutputTable],sizing_mode='fixed')
inputs=column(sliders)
inputs=column(divCSH,inputs)
inputs2=column(sliderSCost)
inputs2=column(divCostSH,inputs2)
inputs=row(inputs,inputs2)# column(sliderSCost)) #test row
inputs=column(inputs,OutputTable)

OptButton.on_click(opt_click)
#curdoc().add_root(grid)
curdoc().add_root(divheader)
curdoc().add_root(row(OptButton,divright))
curdoc().add_root(row(column(plot,divcopy),inputs))# OutputTable))
#curdoc().add_root(divcopy)



