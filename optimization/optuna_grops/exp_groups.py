from strategies.all_tes import *

from optimization.optuna_grops.opt_params import *
group = (    
    # (
    #     STE1_LITE, 
    #     [
    #         (min_period,max_period,1),
    #         (0.5,3,0.1),
    #         (0.1,1,0.1),
    #         (min_period,max_period,1),
    #     ]
    # ),
    (
        PTE30_ETC2, 
        [   
            (0,1),
            (2,200,1),
            (1,),
            (1,),
            (2,half_max_period,1),
            (2,max_period,1),
            (2,max_period,1),
            (2,max_period,1),
            (5,95,1),
            (5,95,1),  
        ]
    ),
        (
        LTE1_CC2, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (max_period, ),
            (2, 13, 1),
            (0.5, 3, 0.1),
            (0, 1),
            (0, 1),
            (2,period2s_max,1),
            (0.01, 0.4, 0.01),
        ]
    ),
    (
        STEML2_TUNNELER, 
        [
            (min_period,max_period,1),
            ["std","maxdev","pct"],
            (0.1,10,0.1),
            (0,0.5,0.001),
   
        ]
    ),
    (
        UTE6_SURVIVALIST, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0.1,3,0.1),
            (0,1),
            (0.1,10,0.1),
            (min_period,max_period,1),
            (5,50,1),
            (0,1),
        ]
    ),
    (
        VTE1_EARTH, 
        [   
            (20,max_period,1),
            (0,1,0.01),
            (4,12,2),
            (0,1,0.01),
            (0,1),
            (0,1,0.01),
            (2,20,1),
            (0,1),
            (0,1),
            (0,1),
        ]
    ),
        (
        WTE3_BATYA, 
        [
            (min_period,max_period,1),
            (0.5, 3, 0.1),
            (0,1),
            (0,1),
            (0,1),
        ]
    ),
)