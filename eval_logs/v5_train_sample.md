# AlphaHoldem V5.0 Training Log Sample

Resumed from `alpha_holdem_v4_final.pt` (1B hands).
Started: 2026-05-07 17:00 EDT.
Total iters logged: 1022

## First 50 iters (startup behaviour: vloss spike then recovery)

```
Device: cuda
GPU: NVIDIA GeForce RTX 4070
Parameters: 8,152,314
V5.0: optimizer reset (fresh Adam moments)
Resumed: 999,222,193 hands, pool=5 (V4->LatestK)

V5.0 trainer: 28 workers @ 200.0 BB
Target: 1,500,000,000 hands
PPO: eps_clip=0.2, delta1=3.0, gamma=0.999
V5.0: epsilon-greedy=0.0 (default 0), both-player collect=ON, latest-K=5
--------------------------------------------------------------------------------
[60901] hands=999,238,610 rew=+2.075 rew100=+2.075 ploss=0.0205 vloss=1125.7596 ent=0.9311 eps=0.000 pool=5 trans=32890 h/s=515 tdec/s=1031 inf_bs=5.3 collect=31.9s ppo=2.4s
[60902] hands=999,255,054 rew=+2.375 rew100=+2.225 ploss=0.0175 vloss=1752.5285 ent=0.8203 eps=0.000 pool=5 trans=24382 h/s=736 tdec/s=1092 inf_bs=5.4 collect=22.3s ppo=1.8s
[60903] hands=999,271,497 rew=+2.100 rew100=+2.183 ploss=0.0118 vloss=1998.1394 ent=0.7734 eps=0.000 pool=5 trans=21017 h/s=989 tdec/s=1264 inf_bs=5.5 collect=16.6s ppo=1.6s
[60904] hands=999,287,930 rew=+4.124 rew100=+2.669 ploss=0.0160 vloss=4388.7984 ent=0.6579 eps=0.000 pool=5 trans=21205 h/s=752 tdec/s=971 inf_bs=4.9 collect=21.8s ppo=1.6s
[60905] hands=999,304,332 rew=+3.862 rew100=+2.907 ploss=0.0080 vloss=4290.1031 ent=0.5718 eps=0.000 pool=5 trans=19419 h/s=826 tdec/s=978 inf_bs=5.0 collect=19.9s ppo=1.4s
[60906] hands=999,320,778 rew=+5.528 rew100=+3.344 ploss=0.0197 vloss=6817.5418 ent=0.4525 eps=0.000 pool=5 trans=18958 h/s=1040 tdec/s=1199 inf_bs=5.6 collect=15.8s ppo=1.3s
[60907] hands=999,337,239 rew=+2.827 rew100=+3.270 ploss=0.0135 vloss=4763.9079 ent=0.5264 eps=0.000 pool=5 trans=19776 h/s=883 tdec/s=1061 inf_bs=5.4 collect=18.6s ppo=1.5s
[60908] hands=999,353,657 rew=+4.499 rew100=+3.424 ploss=0.0083 vloss=6112.6475 ent=0.4779 eps=0.000 pool=5 trans=19248 h/s=928 tdec/s=1087 inf_bs=5.2 collect=17.7s ppo=1.3s
[60909] hands=999,370,055 rew=+3.765 rew100=+3.462 ploss=0.0072 vloss=4547.2047 ent=0.5079 eps=0.000 pool=5 trans=19573 h/s=839 tdec/s=1002 inf_bs=5.3 collect=19.5s ppo=1.5s
[60910] hands=999,386,546 rew=+3.803 rew100=+3.496 ploss=0.0057 vloss=5036.8965 ent=0.5148 eps=0.000 pool=5 trans=19956 h/s=867 tdec/s=1049 inf_bs=5.2 collect=19.0s ppo=1.5s
[60911] hands=999,402,931 rew=+2.744 rew100=+3.427 ploss=0.0083 vloss=4990.8183 ent=0.3962 eps=0.000 pool=5 trans=18615 h/s=1183 tdec/s=1345 inf_bs=5.8 collect=13.8s ppo=1.4s
[60912] hands=999,419,350 rew=+3.291 rew100=+3.416 ploss=0.0073 vloss=4614.0621 ent=0.4634 eps=0.000 pool=5 trans=19335 h/s=862 tdec/s=1015 inf_bs=5.1 collect=19.0s ppo=1.4s
[60913] hands=999,435,767 rew=+2.824 rew100=+3.370 ploss=0.0051 vloss=3166.8619 ent=0.4694 eps=0.000 pool=5 trans=18765 h/s=1045 tdec/s=1194 inf_bs=5.5 collect=15.7s ppo=1.3s
[60914] hands=999,452,172 rew=+2.571 rew100=+3.313 ploss=0.0061 vloss=2823.9968 ent=0.5900 eps=0.000 pool=5 trans=19566 h/s=909 tdec/s=1084 inf_bs=5.4 collect=18.1s ppo=1.4s
[60915] hands=999,468,580 rew=+4.186 rew100=+3.372 ploss=0.0118 vloss=6586.2886 ent=0.4466 eps=0.000 pool=5 trans=19176 h/s=916 tdec/s=1070 inf_bs=5.1 collect=17.9s ppo=1.4s
[60916] hands=999,484,995 rew=+3.001 rew100=+3.348 ploss=0.0015 vloss=4279.0498 ent=0.5843 eps=0.000 pool=5 trans=19634 h/s=943 tdec/s=1128 inf_bs=5.2 collect=17.4s ppo=1.4s
[60917] hands=999,501,452 rew=+3.949 rew100=+3.384 ploss=0.0029 vloss=4549.5611 ent=0.6452 eps=0.000 pool=5 trans=20851 h/s=870 tdec/s=1102 inf_bs=5.3 collect=18.9s ppo=1.6s
[60918] hands=999,517,873 rew=+4.774 rew100=+3.461 ploss=0.0045 vloss=7001.3748 ent=0.5747 eps=0.000 pool=5 trans=21224 h/s=929 tdec/s=1201 inf_bs=5.5 collect=17.7s ppo=1.5s
[60919] hands=999,534,300 rew=+5.567 rew100=+3.572 ploss=0.0032 vloss=6847.6990 ent=0.6199 eps=0.000 pool=5 trans=21022 h/s=869 tdec/s=1111 inf_bs=5.4 collect=18.9s ppo=1.5s
[60920] hands=999,550,718 rew=+2.950 rew100=+3.541 ploss=0.0041 vloss=4278.9376 ent=0.6831 eps=0.000 pool=5 trans=21935 h/s=780 tdec/s=1042 inf_bs=5.1 collect=21.0s ppo=1.6s
[60921] hands=999,567,125 rew=+2.979 rew100=+3.514 ploss=0.0021 vloss=4590.7360 ent=0.7103 eps=0.000 pool=5 trans=22685 h/s=766 tdec/s=1059 inf_bs=5.4 collect=21.4s ppo=1.7s
[60922] hands=999,583,529 rew=+5.071 rew100=+3.585 ploss=0.0041 vloss=5743.7874 ent=0.6912 eps=0.000 pool=5 trans=22577 h/s=881 tdec/s=1212 inf_bs=5.6 collect=18.6s ppo=1.6s
[60923] hands=999,599,974 rew=+2.078 rew100=+3.519 ploss=0.0032 vloss=3119.8379 ent=0.7465 eps=0.000 pool=5 trans=22080 h/s=866 tdec/s=1162 inf_bs=5.5 collect=19.0s ppo=1.6s
[60924] hands=999,616,367 rew=+5.670 rew100=+3.609 ploss=0.0129 vloss=5638.9016 ent=0.6792 eps=0.000 pool=5 trans=21514 h/s=798 tdec/s=1048 inf_bs=5.2 collect=20.5s ppo=1.6s
[60925] hands=999,632,769 rew=+4.895 rew100=+3.660 ploss=0.0063 vloss=5801.5589 ent=0.7070 eps=0.000 pool=5 trans=23192 h/s=756 tdec/s=1069 inf_bs=5.5 collect=21.7s ppo=1.7s
[60926] hands=999,649,175 rew=+5.188 rew100=+3.719 ploss=0.0073 vloss=6516.0574 ent=0.6805 eps=0.000 pool=5 trans=24458 h/s=681 tdec/s=1015 inf_bs=5.2 collect=24.1s ppo=1.7s
[60927] hands=999,665,607 rew=+2.741 rew100=+3.683 ploss=0.0093 vloss=4477.3858 ent=0.7497 eps=0.000 pool=5 trans=23768 h/s=850 tdec/s=1229 inf_bs=5.4 collect=19.3s ppo=1.6s
[60928] hands=999,682,073 rew=+3.618 rew100=+3.681 ploss=0.0054 vloss=3855.9172 ent=0.8387 eps=0.000 pool=5 trans=27423 h/s=706 tdec/s=1176 inf_bs=5.5 collect=23.3s ppo=2.0s
[60929] hands=999,698,472 rew=+5.402 rew100=+3.740 ploss=0.0040 vloss=5610.1869 ent=0.7829 eps=0.000 pool=5 trans=27619 h/s=608 tdec/s=1023 inf_bs=5.3 collect=27.0s ppo=2.0s
[60930] hands=999,714,892 rew=+5.829 rew100=+3.810 ploss=0.0020 vloss=5788.8956 ent=0.7552 eps=0.000 pool=5 trans=27234 h/s=638 tdec/s=1058 inf_bs=5.0 collect=25.7s ppo=1.9s
[60931] hands=999,731,347 rew=+5.933 rew100=+3.878 ploss=0.0051 vloss=5444.5540 ent=0.7362 eps=0.000 pool=5 trans=28390 h/s=636 tdec/s=1097 inf_bs=5.0 collect=25.9s ppo=2.0s
[60932] hands=999,747,780 rew=+5.647 rew100=+3.933 ploss=0.0046 vloss=6014.6706 ent=0.7111 eps=0.000 pool=5 trans=26022 h/s=677 tdec/s=1073 inf_bs=5.0 collect=24.3s ppo=1.9s
[60933] hands=999,764,190 rew=+4.861 rew100=+3.961 ploss=0.0010 vloss=5693.2397 ent=0.7188 eps=0.000 pool=5 trans=26558 h/s=616 tdec/s=998 inf_bs=5.0 collect=26.6s ppo=1.9s
[60934] hands=999,780,617 rew=+6.121 rew100=+4.025 ploss=0.0053 vloss=4954.5510 ent=0.7207 eps=0.000 pool=5 trans=27327 h/s=569 tdec/s=947 inf_bs=4.9 collect=28.9s ppo=2.0s
[60935] hands=999,797,022 rew=+6.009 rew100=+4.082 ploss=0.0060 vloss=6699.7809 ent=0.6588 eps=0.000 pool=5 trans=26069 h/s=602 tdec/s=957 inf_bs=5.0 collect=27.2s ppo=1.9s
[60936] hands=999,813,491 rew=+5.702 rew100=+4.127 ploss=0.0055 vloss=6090.2007 ent=0.7191 eps=0.000 pool=5 trans=26856 h/s=673 tdec/s=1097 inf_bs=5.1 collect=24.5s ppo=1.8s
[60937] hands=999,829,907 rew=+6.638 rew100=+4.195 ploss=0.0073 vloss=6635.7857 ent=0.6695 eps=0.000 pool=5 trans=27559 h/s=593 tdec/s=995 inf_bs=5.2 collect=27.7s ppo=1.9s
[60938] hands=999,846,307 rew=+6.048 rew100=+4.243 ploss=0.0041 vloss=5389.8773 ent=0.6731 eps=0.000 pool=5 trans=28644 h/s=590 tdec/s=1031 inf_bs=5.0 collect=27.8s ppo=2.0s
[60939] hands=999,862,747 rew=+5.892 rew100=+4.286 ploss=0.0096 vloss=5876.1137 ent=0.6242 eps=0.000 pool=5 trans=28183 h/s=742 tdec/s=1272 inf_bs=6.0 collect=22.1s ppo=2.0s
```

## Last 30 iters (stable, no gaming contention)

```
[61868] hands=1,015,112,149 rew=-0.078 rew100=+0.073 ploss=0.0041 vloss=215.7285 ent=0.5390 eps=0.000 pool=5 trans=24069 h/s=686 tdec/s=1006 inf_bs=5.1 collect=23.9s ppo=1.9s
[61869] hands=1,015,128,591 rew=-0.028 rew100=+0.071 ploss=0.0020 vloss=181.3486 ent=0.5535 eps=0.000 pool=5 trans=23329 h/s=741 tdec/s=1051 inf_bs=5.4 collect=22.2s ppo=1.7s
[61870] hands=1,015,145,021 rew=-0.086 rew100=+0.071 ploss=0.0008 vloss=202.6685 ent=0.5537 eps=0.000 pool=5 trans=23322 h/s=705 tdec/s=1001 inf_bs=5.1 collect=23.3s ppo=1.7s
[61871] hands=1,015,161,436 rew=-0.201 rew100=+0.068 ploss=0.0017 vloss=185.8841 ent=0.5324 eps=0.000 pool=5 trans=22750 h/s=642 tdec/s=890 inf_bs=5.1 collect=25.6s ppo=1.7s
[61872] hands=1,015,177,855 rew=-0.165 rew100=+0.067 ploss=0.0035 vloss=183.7943 ent=0.5431 eps=0.000 pool=5 trans=23934 h/s=715 tdec/s=1043 inf_bs=5.1 collect=23.0s ppo=1.8s
[61873] hands=1,015,194,250 rew=-0.247 rew100=+0.063 ploss=0.0018 vloss=170.7686 ent=0.5169 eps=0.000 pool=5 trans=26344 h/s=709 tdec/s=1139 inf_bs=5.7 collect=23.1s ppo=1.8s
[61874] hands=1,015,210,710 rew=+0.122 rew100=+0.064 ploss=0.0041 vloss=191.4979 ent=0.4918 eps=0.000 pool=5 trans=25366 h/s=676 tdec/s=1041 inf_bs=5.2 collect=24.4s ppo=1.8s
[61875] hands=1,015,227,131 rew=+0.117 rew100=+0.063 ploss=0.0036 vloss=220.0599 ent=0.4994 eps=0.000 pool=5 trans=25778 h/s=682 tdec/s=1070 inf_bs=5.4 collect=24.1s ppo=1.9s
[61876] hands=1,015,243,536 rew=+0.088 rew100=+0.059 ploss=0.0003 vloss=292.0535 ent=0.4878 eps=0.000 pool=5 trans=25105 h/s=526 tdec/s=804 inf_bs=4.8 collect=31.2s ppo=1.8s
[61877] hands=1,015,259,926 rew=+0.158 rew100=+0.059 ploss=0.0009 vloss=420.0061 ent=0.4605 eps=0.000 pool=5 trans=25753 h/s=623 tdec/s=978 inf_bs=5.3 collect=26.3s ppo=2.0s
[61878] hands=1,015,276,342 rew=+0.411 rew100=+0.063 ploss=0.0065 vloss=336.0014 ent=0.4689 eps=0.000 pool=5 trans=24040 h/s=598 tdec/s=876 inf_bs=5.1 collect=27.4s ppo=1.7s
[61879] hands=1,015,292,796 rew=+0.390 rew100=+0.065 ploss=0.0002 vloss=516.4838 ent=0.4450 eps=0.000 pool=5 trans=23919 h/s=672 tdec/s=977 inf_bs=5.4 collect=24.5s ppo=1.7s
[61880] hands=1,015,309,217 rew=+0.273 rew100=+0.068 ploss=0.0014 vloss=492.3233 ent=0.4282 eps=0.000 pool=5 trans=26021 h/s=633 tdec/s=1003 inf_bs=5.3 collect=26.0s ppo=1.9s
[61881] hands=1,015,325,651 rew=+0.264 rew100=+0.070 ploss=0.0012 vloss=475.0251 ent=0.4601 eps=0.000 pool=5 trans=25155 h/s=683 tdec/s=1046 inf_bs=5.2 collect=24.0s ppo=1.7s
[61882] hands=1,015,342,145 rew=+0.132 rew100=+0.071 ploss=0.0060 vloss=470.0954 ent=0.4738 eps=0.000 pool=5 trans=23731 h/s=651 tdec/s=937 inf_bs=5.1 collect=25.3s ppo=1.7s
[61883] hands=1,015,358,544 rew=-0.079 rew100=+0.068 ploss=0.0165 vloss=419.0014 ent=0.5095 eps=0.000 pool=5 trans=22811 h/s=640 tdec/s=891 inf_bs=5.1 collect=25.6s ppo=1.7s
[61883] hands=1,015,358,544 rew=-0.079 rew100=+0.068 ploss=0.0165 vloss=419.0014 ent=0.5095 eps=0.000 pool=5 trans=22811 h/s=640 tdec/s=891 inf_bs=5.1 collect=25.6s ppo=1.7s
[61884] hands=1,015,374,970 rew=+0.100 rew100=+0.068 ploss=0.0128 vloss=259.1134 ent=0.5355 eps=0.000 pool=5 trans=21992 h/s=664 tdec/s=888 inf_bs=5.1 collect=24.8s ppo=1.7s
[61885] hands=1,015,391,412 rew=-0.207 rew100=+0.063 ploss=0.0038 vloss=233.0072 ent=0.5415 eps=0.000 pool=5 trans=22759 h/s=649 tdec/s=898 inf_bs=4.9 collect=25.3s ppo=1.7s
[61886] hands=1,015,407,833 rew=-0.001 rew100=+0.058 ploss=0.0057 vloss=263.1006 ent=0.5329 eps=0.000 pool=5 trans=23762 h/s=550 tdec/s=796 inf_bs=4.9 collect=29.8s ppo=1.7s
[61887] hands=1,015,424,278 rew=-0.025 rew100=+0.056 ploss=0.0096 vloss=188.4815 ent=0.5700 eps=0.000 pool=5 trans=23175 h/s=920 tdec/s=1296 inf_bs=5.9 collect=17.9s ppo=1.7s
[61888] hands=1,015,440,675 rew=-0.086 rew100=+0.053 ploss=0.0012 vloss=212.0746 ent=0.5758 eps=0.000 pool=5 trans=22335 h/s=708 tdec/s=965 inf_bs=5.2 collect=23.1s ppo=1.6s
[61889] hands=1,015,457,066 rew=-0.168 rew100=+0.051 ploss=0.0036 vloss=186.3007 ent=0.5827 eps=0.000 pool=5 trans=21881 h/s=781 tdec/s=1042 inf_bs=5.4 collect=21.0s ppo=1.6s
[61890] hands=1,015,473,512 rew=-0.130 rew100=+0.048 ploss=0.0002 vloss=145.3266 ent=0.5806 eps=0.000 pool=5 trans=21827 h/s=793 tdec/s=1052 inf_bs=5.1 collect=20.7s ppo=1.6s
[61891] hands=1,015,489,929 rew=+0.065 rew100=+0.048 ploss=0.0020 vloss=160.1507 ent=0.5769 eps=0.000 pool=5 trans=22179 h/s=682 tdec/s=921 inf_bs=5.0 collect=24.1s ppo=1.6s
[61892] hands=1,015,506,327 rew=-0.013 rew100=+0.046 ploss=0.0006 vloss=188.7270 ent=0.5797 eps=0.000 pool=5 trans=22004 h/s=692 tdec/s=928 inf_bs=5.0 collect=23.7s ppo=1.6s
[61893] hands=1,015,522,740 rew=+0.072 rew100=+0.044 ploss=0.0046 vloss=204.6751 ent=0.5978 eps=0.000 pool=5 trans=21180 h/s=619 tdec/s=799 inf_bs=4.9 collect=26.5s ppo=1.5s
[61894] hands=1,015,539,198 rew=+0.087 rew100=+0.043 ploss=0.0011 vloss=298.0426 ent=0.5988 eps=0.000 pool=5 trans=21738 h/s=676 tdec/s=893 inf_bs=5.0 collect=24.4s ppo=1.6s
[61895] hands=1,015,555,674 rew=-0.077 rew100=+0.040 ploss=0.0055 vloss=301.7969 ent=0.6084 eps=0.000 pool=5 trans=22128 h/s=676 tdec/s=908 inf_bs=5.0 collect=24.4s ppo=1.6s
[61896] hands=1,015,572,069 rew=-0.055 rew100=+0.038 ploss=0.0033 vloss=241.3179 ent=0.6193 eps=0.000 pool=5 trans=22750 h/s=725 tdec/s=1005 inf_bs=5.2 collect=22.6s ppo=1.7s
```
