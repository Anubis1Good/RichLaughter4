from strategies.all_tes import *

from optimization.optuna_grops.opt_params import *
group = (    
    (
        PTE30_ETC, 
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



)