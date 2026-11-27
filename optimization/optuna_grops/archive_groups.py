from strategies.all_tes import *

# (min, max, step)
from optimization.optuna_grops.opt_params import *
group = (
    (
        PTE2_DDCrWork, 
        [
            (2,max_period,1),
        ]
    ),

    (
        LTE1_BORSCH, 
        [
            (2, max_period, 1),
            (2, max_period, 1),
        ]
    ),
    (
        LTE1_PHOBO, 
        [
            (2, max_period, 1),
            (0.5,4,0.1),
            (max_period, ),
        ]
    ),
    (
        LTE1_PHOGA, 
        [
            (2, max_period, 1),
            (0.5,4,0.1),
            (2, max_period, 1),
            (max_period, ),
        ]
    ),


        (
        PTE11_KUSURUKEN, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0, 50, 1),    
            ('c', 'hl'),    
            (max_period,),
        ]
    ),
        (
        PTE13_DWDDCr, 
        [
            (min_period,max_period,1),
            (5, 45, 1),
            (min_period,max_period,1),
        ]
    ),

        (
        PTE17_ARCHON, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0, 50, 1),
            (max_period,),
        ]
    ),
        (
        PTE18_BLAZE, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (5, 40, 1),
            (5, 40, 1),
            (0, 1),
            (max_period,),
        ]
    ),

    (
        PTE18_ANDUIN, 
        [
            (min_period,max_period,1),
            (0.5,4,0.1),
            (min_period,max_period,1),
            (5, 40, 1),
            (5, 70, 1),
            (2, half_max_period, 1),
            (0,1),
            (max_period, ),
        ]
    ),
    (
        PTE19_ANUBARAK, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (5, 40, 1),
            (5, 50, 1),
            (0, 100, 1),
            (0,1),
            (max_period, ),
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
        LTE1_BIBI2, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            ('cmo','rsi','rsi_tw','williams_r','mfi','ultimate_oscillator','cci','%d'),
            (max_period, ),
            (2,period2s_max,1),
            (0.01, 0.4, 0.01),
        ]
    ),
        (
        LTE1_IRONANNY2, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (max_period, ),
            (2,8,1),
            (2,period2s_max,1),
            (0.01, 0.4, 0.01),
        ]
    ),

       (
        UTE8_SOLDIER, 
        [
            (1,20,1),
            (min_period,max_period,1),
            (20,max_period,1),
            (0,1,0.01),
            (4,12,2),
            (0,1,0.01),
            (10,50,1),
            (0,1),
            (0,99,1),
            (0,99,1),
            (0,99,1),
            (0,99,1),
            (0,99,1),
            (0,99,1),
            (0,99,1),
            (0,99,1),
        ]
    ),
    
    
        (
        WTE10_sleep, 
        [
            (2,max_period,1),
            (0.5,3,0.1),
            (2,max_period,1),
            (max_period,),
            (0,1),

        ]
    ),
    # (
    #     WTE10_sonny, 
    #     [
    #         (2,max_period,1),
    #         (0.5,3,0.1),
    #         (2,max_period,1),
    #         (max_period,),
    #         (0,1),
    #         (0.01, 0.99, 0.01),
    #     ]
    # ),
        (
        VTE1_MOON, 
        [
            (2,20,1),
            (20,max_period,1),
            (0,1,0.01),
            (4,12,2),
            (0,1,0.01),
            (0,1),
            (0,1),
            (0,1),
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
)