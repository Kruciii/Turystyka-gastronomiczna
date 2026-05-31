# Turystyka gastronomiczna - projekt z ekonometrii przestrzennej (WAP)

## Strona tytulowa
- Tytul pracy: Turystyka gastronomiczna - porownanie krajow UE metoda WAP
- Imie i nazwisko autora: Antoni Kindlik, Nikola Mazurczak, Maciej Bartoszuk
- Kierunek studiow: Informatyka i Ekonometria
- Rok studiow: 3

## Uzasadnienie wyboru tematyki
Badane zjawisko dotyczy rozwoju turystyki gastronomicznej w krajach UE, rozumianego jako polaczenie infrastruktury gastronomicznej, dziedzictwa kulinarnego oraz atrakcyjnosci cenowej i sezonowosci popytu. Teoretycznie zjawisko jest ksztaltowane przez czynniki mikroekonomiczne (liczba firm i zatrudnienia w gastronomii), makroekonomiczne (poziom cen w sektorze HoReCa) oraz instytucjonalne (ochrona produktow regionalnych). Zmienne diagnostyczne dobrano tak, aby uchwycic wielowymiarowy charakter konkurencyjnosci turystyki gastronomicznej, zgodnie z logika powiazan ekonomicznych i dostepnoscia danych.

## Sformulowanie celu badania
- Cel glowny: ocena i porownanie krajow pod wzgledem rozwoju turystyki gastronomicznej z wykorzystaniem metod WAP.
- Cele szczegolowe:
	1) przygotowanie i selekcja zmiennych diagnostycznych,
	2) zbudowanie rankingow kilkoma metodami,
	3) ocena zgodnosci metod i wybor metody najlepiej odzwierciedlajacej zjawisko.


## Krotki opis metod wykorzystanych w pracy
Zastosowano wielowymiarowa analize porownawcza: selekcje zmiennych na podstawie wspolczynnika zmiennosci Vj i korelacji, a nastepnie porzadkowanie liniowe metoda Hellwiga, TOPSIS, BZW, syntetyczna miara K. Kukuly, suma rang oraz metode iteracyjna. Zgodnosc rankingow porownano na podstawie korelacji rang Spearmana. Opis ma charakter skrocony, bez przepisywania z podrecznikow.

## Metody z wykladow nieuzyte w kodzie
- Normalizacje i przeksztalcenia: standaryzacja Webbera (mediana i MAD), normalizacja do przedzialu [-1,1], dodatkowe warianty przeksztalcen ilorazowych, transformacje nominant do stymulant (ilorazowe i roznicowe).
- Miary porzadkowania: metoda sum standaryzowanych oraz jej wersja wazona, ogolny TMR z wzorcem rozwoju poza wariantem Hellwiga.
- Wazenie zmiennych: wagi oparte o zmiennosc, wagi oparte o korelacje, metoda punktowa K. Kukuly.
- Klasyfikacja: metody hierarchiczne inne niz Warda (najblizszego i najdalszego sasiedztwa, sredniej grupowej, mediany, srodka ciezkosci) oraz metody niehierarchiczne (k-srednich, Forgy-Jancey, Wishart).
- Analiza przestrzenna: statystyka C Geary'ego, statystyki join-count, wykres Morana i testy istotnosci (normalny, randomizowany, permutacyjny).

## Wyniki przeprowadzonych badan
Wyniki generowane sa w notatniku [1.ipynb](1.ipynb) na podstawie danych z [data.csv](data.csv). W tabelach i rankingach sa zamieszczone krotkie komentarze interpretacyjne. W sytuacjach, gdy wyniki w kolejnych etapach sa podobne, komentarze odwolują sie do wczesniejszych tabel, aby nie powtarzac tresci.

## Podsumowanie i wnioski
Cele badania zostaly zrealizowane: dokonano selekcji cech, zbudowano rankingi kilkoma metodami oraz porownano ich zgodnosc. W czolowce metod klasycznych najczesciej pojawiaja sie Wlochy i Francja, a nizsze pozycje zajmuja Czechy i Polska. Jako metode wiodaca przyjeto sume rang z uwagi na najwyzsza srednia zgodnosc z innymi rankingami. Analiza przestrzenna (np. Moran I) nie byla wykonana z powodu braku danych o polozeniu, a dynamika w czasie nie byla badana z powodu braku danych wieloletnich.



## Dane i srodowisko
- Dane: [data.csv](data.csv)
- Analizy: [1.ipynb](1.ipynb)
- Wymagane biblioteki: pandas, numpy

## Jak uruchomic
1. Otworz [1.ipynb](1.ipynb).
2. Uruchom kolejne komorki od gory do dolu.
3. Sprawdz wygenerowane tabele i komentarze w sekcji wynikow.
