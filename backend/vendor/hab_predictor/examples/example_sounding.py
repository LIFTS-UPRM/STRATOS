"""
Example Sounding based Simulation

ASTRA High Altitude Balloon Flight Planner

University of Southampton
"""
from datetime import datetime
from astra.simulator import *


if __name__ == "__main__":
    soundingFile = os.path.join(os.path.dirname(__file__), 'sp.sounding')


    simEnvironment = soundingEnvironment(launchSiteLat=50.2245,         # deg
                                         launchSiteLon=-5.3069,         # deg
                                         launchSiteElev=60,             # m
                                         distanceFromSounding=0,        # km
                                         timeFromSounding=3,            # hours
                                         inflationTemperature=10.5,     # degC
                                         dateAndTime=datetime.now(),
                                         soundingFile=soundingFile,
                                         debugging=True)
    # TODO: Add an example sounding file, with description of how to create one
    # simEnvironment.load()

    # Launch setup
    simFlight = flight(environment=simEnvironment,
                       balloonGasType='Helium',
                       balloonModel='TA800',
                       nozzleLift=1,                                # kg
                       payloadTrainWeight=0.433,                    # kg
                       parachuteModel='SPH36',
                       numberOfSimRuns=10,
                       trainEquivSphereDiam=0.1,                    # m
                       floatingFlight=False,
                       floatingAltitude=30000,                      # m
                       excessPressureCoeff=1,
                       outputFile=os.path.join('.', 'astra_output_sounding'),
                       debugging=True,
                       log_to_file=True)

    # Run the simulation
    simFlight.run()