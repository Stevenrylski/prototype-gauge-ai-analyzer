# Failing Examples

<!--
Absichtliche Fehlerbeispiele zum Testen des Analyzers. Diese Szenarien
verwenden die bereits vorhandenen Steps mit falschen Erwartungswerten,
damit ein echter Gauge-Lauf fehlschlaegt und der Report echte Fehler enthaelt.
Nicht Teil der eigentlichen Testsuite.
-->

## Single word vowel count is wrong

* The word "gauge" has "5" vowels.

## Table vowel count is wrong

* Almost all words have vowels

     |Word  |Vowel Count|
     |------|-----------|
     |Gauge |5          |
     |Mingle|2          |
     |Snap  |1          |

## Duplicate failure first scenario

* The word "rhythm" has "3" vowels.

## Duplicate failure second scenario

* The word "rhythm" has "3" vowels.
