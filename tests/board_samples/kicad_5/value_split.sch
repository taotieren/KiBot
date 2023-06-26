EESchema Schematic File Version 4
EELAYER 30 0
EELAYER END
$Descr A4 11693 8268
encoding utf-8
Sheet 1 1
Title "Value field split test"
Date "2023-05-03"
Rev ""
Comp "Instituto Nacional de Tecnología Industrial - CMNT"
Comment1 "KiBot"
Comment2 ""
Comment3 ""
Comment4 ""
$EndDescr
$Comp
L Device:C C1
U 1 1 64524E13
P 3000 2150
F 0 "C1" H 3115 2197 50  0000 L CNN
F 1 "1uF 0603 ±30%" H 3115 2104 50  0000 L CNN
F 2 "" H 3038 2000 50  0001 C CNN
F 3 "~" H 3000 2150 50  0001 C CNN
	1    3000 2150
	1    0    0    -1  
$EndComp
$Comp
L Device:C C2
U 1 1 645255C4
P 4000 2150
F 0 "C2" H 4115 2197 50  0000 L CNN
F 1 "100p 0805 NPO 50V" H 4115 2104 50  0000 L CNN
F 2 "" H 4038 2000 50  0001 C CNN
F 3 "~" H 4000 2150 50  0001 C CNN
	1    4000 2150
	1    0    0    -1  
$EndComp
$Comp
L Device:R R1
U 1 1 645257E4
P 3000 2650
F 0 "R1" H 3070 2697 50  0000 L CNN
F 1 "12k 1% 0402 1/8W" H 3070 2604 50  0000 L CNN
F 2 "" V 2930 2650 50  0001 C CNN
F 3 "~" H 3000 2650 50  0001 C CNN
	1    3000 2650
	1    0    0    -1  
$EndComp
$Comp
L Device:R R2
U 1 1 64525CC7
P 4000 2650
F 0 "R2" H 4070 2697 50  0000 L CNN
F 1 "1M 10%" H 4070 2604 50  0000 L CNN
F 2 "" V 3930 2650 50  0001 C CNN
F 3 "~" H 4000 2650 50  0001 C CNN
F 4 "5%" H 4000 2650 50  0001 C CNN "tolerance"
	1    4000 2650
	1    0    0    -1  
$EndComp
$Comp
L Device:L L1
U 1 1 645261A6
P 3000 3150
F 0 "L1" H 3055 3197 50  0000 L CNN
F 1 "3n3 0603 10%" H 3055 3104 50  0000 L CNN
F 2 "" H 3000 3150 50  0001 C CNN
F 3 "~" H 3000 3150 50  0001 C CNN
	1    3000 3150
	1    0    0    -1  
$EndComp
$Comp
L Device:L L2
U 1 1 645266D9
P 4000 3150
F 0 "L2" H 4056 3197 50  0000 L CNN
F 1 "1nH 100V" H 4056 3104 50  0000 L CNN
F 2 "" H 4000 3150 50  0001 C CNN
F 3 "~" H 4000 3150 50  0001 C CNN
F 4 "50V" H 4000 3150 50  0001 C CNN "Voltage"
	1    4000 3150
	1    0    0    -1  
$EndComp
$EndSCHEMATC