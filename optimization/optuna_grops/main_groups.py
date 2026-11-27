from strategies.all_tes import *

from optimization.optuna_grops.opt_params import *
# (min, max, step)

# 13.10.2026 каждется надо ввести еще параметр min_period. Ибо 2 - это очень маленький период. Надо хотя бы 5
group = (

    (
        PTE4_U4, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (max_period,),
            ("DC","VG","BB","VC","WC","SC"),
            ("rsi","mfi","s","uo","velcro","pedal","wpedal","diff_pedals","real_pedal", "real_wpedal", "real_diff_pedals"),
            (2,period2s_max,1),
            (0.01, 0.5, 0.01),
        ]
    ),


        (
        PTE11_RAYMIYAMOTO,
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0.5,5,0.1),
            (0.5,5,0.1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            ("rsi","mfi","s","uo","velcro","pedal","wpedal","real_pedal", "real_wpedal"),
            ("rsi","mfi","s","uo","velcro","pedal","wpedal","real_pedal", "real_wpedal"),
            (2,period2s_max,1),
            (max_period,),
            (min_period,max_period,1),
            (10,90,1),
            (1,50,1),
            (1,50,1),
            (1,50,1),
            (1,50,1),
            (0,1),
            (0,20,1),
        ]
    ),
    (
        PTE11_SAYATAKAGI,
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0.5,5,0.1),
            (0.5,5,0.1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            ("rsi","mfi","s","uo","velcro","pedal","wpedal","real_pedal", "real_wpedal"),
            ("rsi","mfi","s","uo","velcro","pedal","wpedal","real_pedal", "real_wpedal"),
            (2,period2s_max,1),
            (max_period,),
            (min_period,max_period,1),
            (10,90,1),
            (1,50,1),
            (1,50,1),
            (1,50,1),
            (0,1),
            (0,20,1),
        ]
    ),
    (
        PTE11_ALICEMARASATO,
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0.5,5,0.1),
            (0.5,5,0.1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            ("rsi","mfi","s","uo","velcro","pedal","wpedal","real_pedal", "real_wpedal"),
            ("rsi","mfi","s","uo","velcro","pedal","wpedal","real_pedal", "real_wpedal"),
            (2,period2s_max,1),
            (max_period,),
            (min_period,max_period,1),
            (10,90,1),
            (1,50,1),
            (1,50,1),
            (1,50,1),
            (0,1),
            (0,20,1),
            (0,1),
        ]
    ),
    (
        PTE11_SHIZUKAMARIKAWA,
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0.5,5,0.1),
            (0.5,5,0.1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            ("rsi","mfi","s","uo","velcro","pedal","wpedal","real_pedal", "real_wpedal"),
            ("rsi","mfi","s","uo","velcro","pedal","wpedal","real_pedal", "real_wpedal"),
            (2,period2s_max,1),
            (max_period,),
            (min_period,max_period,1),
            (10,90,1),
            (1,50,1),
            (1,50,1),
            (1,50,1),
            (0,1),
            (0,20,1),
            (0,1),
        ]
    ),

    (
        PTE13_DUNE, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0.01,0.4,0.01),
            (max_period,),
            (min_period,max_period,1),
            (0,0.3,0.01),
        ]
    ),
    (
        PTE14_RWDDCr, 
        [
            (min_period,max_period,1),
            (1,50,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (max_period,),
        ]
    ),
    (
        PTE14_REGAL, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (1,50,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (max_period,),
        ]
    ),
    (
        PTE14_RANGER, 
        [
            (2, half_max_period, 1),
            (1,50,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (5, 100, 1),
            (5, 100, 1),
        ]
    ),
    (
        PTE14_RENEGADE, 
        [
            (2, half_max_period, 1),
            (1,50,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (5, 100, 1),
            (5, 100, 1),
        ]
    ),

    (
        PTE17_PHOENIX, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0, 50, 1),
            (0, 1),
            (max_period,),
        ]
    ),
    (
        PTE17_ZEALOT, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0, 50, 1),
            (max_period,),
        ]
    ),
    (
        PTE17_AIUR, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0, 50, 1),
            (0, 1),
            (max_period,),
            (0, 1, 0.1),
        ]
    ),
    (
        PTE17_SELENDIS, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0, 50, 1),
            (max_period,),
            (min_period,max_period,1),
        ]
    ),
    (
        PTE17_ALDERA, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0, 50, 1),
            (max_period,),
            (min_period,max_period,1),
            (0, 50, 1),
        ]
    ),


    (
        PTE26_UNKNOWN, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0, 50, 1),
            (0, 50, 1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (max_period,),
            (0, 1),
        ]
    ),
    (
        PTE26_JUNKRAT, 
        [
            (min_period,max_period,1),
            (0, 50, 1),
            (0, 50, 1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0.05, 1 , 0.05),
        ]
    ),
        (
        PTE26_GAZLOWE, 
        [
            (min_period,max_period,1),
            (0, 50, 1),
            (0, 50, 1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0,50,1),
        ]
    ),
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



    (
        LTE1_IGOGOSHA2, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            ('cmo','rsi','rsi_tw','williams_r','mfi','ultimate_oscillator','cci','%d'),
            (2,period2s_max,1),
            (0.01, 0.4, 0.01),
            (min_period,max_period,1),
            (max_period, ),
        ]
    ),

    (
        LTE1_LAKSAe, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
        ]
    ),


    (
        LTE1_PIN, 
        [
            (min_period,max_period,1),
            (2, max_period//8, 1),
            (1,50,1),
            (3,7,1)
        ]
    ),

    (
        LTE2_DRG, 
        [
            (min_period,max_period,1),
            (0.5,3,0.1),
            (min_period,max_period,1),
            (1,50,1),
            (1,50,1),
            (0,1)
        ]
    ),
    (
        LTE2_DRINKER, 
        [
            (min_period,max_period,1),
            (0.5,3,0.1),
            (min_period,max_period,1),
            (1,50,1),
            (1,50,1),
            (0,1)
        ]
    ),
    (
        LTE2_FENNEC, 
        [
            (min_period,max_period,1),
            (0.5,3,0.1),
            (min_period,max_period,1),
            (1,50,1),
            (1,50,1),
            (0.5,2,0.1),
            (0,1)
        ]
    ),
    (
        LTE2_HOTS, 
        [
            (min_period,max_period,1),
            (0.5,3,0.1),
            (min_period,max_period,1),
            (1,50,1),
            (1,50,1),
            (0,1)
        ]
    ),
    (
        LTE2_LOGAN, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (10,90,1),
        ]
    ),
    (
        LTE2_LYNX, 
        [
            (min_period,max_period,1),
            (0.5,3,0.1),
            (min_period,max_period,1),
            (0.5,2,0.1),
            (0,1)
        ]
    ),
    (
        LTE3a_LOTR, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (0,50,1),
            (max_period,),
   
        ]
    ),
    (
        STE1_LITE, 
        [
            (min_period,max_period,1),
            (0.5,3,0.1),
            (0.1,1,0.1),
            (min_period,max_period,1),
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
        UTE9_GRAVY2, 
        [
            (20,max_period,1),
            (0,1,0.01),
            (4,12,2),
            (0,0.5,0.01),
            (0.1,2,0.05),
            (0,1),
        ]
    ),
    
    (
        UTE9_POLITICIAN, 
        [
            (20,max_period,1),
            (0,1,0.01),
            (4,12,2),
            (0,0.5,0.01),
            (0,1),
            (min_period,max_period,1),
            (5,50,1),
        ]
    ),
    (
        UTE9_ASTRAL, 
        [
            (min_period,max_period,1),
            (0,10,0.1),
            (0.05,1,0.01),
        ]
    ),
    (
        UTE9_MEDIUM, 
        [
            (min_period,max_period,1),
            (0,10,0.1),
            (0.05,1,0.01),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (max_period,),
            (0,50,1),
        ]
    ),
    (
        UTE9_TRACKER, 
        [
            (min_period,max_period,1),
            (0,10,0.1),
            (0.05,1,0.01),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (max_period,),
            (0,50,1),
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
    (
        WTE4_DOG, 
        [
            (min_period,max_period,1),
            (1, 50, 1),
        ]
    ),
    (
        WTE4_PUPPY, 
        [
            (min_period,max_period,1),
            (1, 50, 1),
            (1, 50, 1),
        ]
    ),

    (
        WTE7_PARADOX2, 
        [
            (min_period,max_period,1),
            (0.3,3,0.1),
            (min_period,max_period,1),
            (0.3,3,0.1),
        ]
    ),
    (
        WTE8_MOUSE, 
        [
            (min_period,max_period,1),
            (min_period,max_period,1),
            (1, 50, 1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period,max_period,1),
            (min_period, half_max_period, 1),
            (5, 80, 1),
            (max_period,),
            (0.01, 0.4, 0.01),

        ]
    ),
)
