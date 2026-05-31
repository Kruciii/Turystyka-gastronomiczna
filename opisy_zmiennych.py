VARIABLE_DESCRIPTIONS = {
    "liczba przedsiębiorstw z branży gastronomicznej i mobilnej gastronomii": (
        "Liczba podmiotow dzialajacych w sektorze gastronomii oraz mobilnej gastronomii; "
        "opisuje skale rynku i jego dostepnosc dla turystow."
    ),
    "5-letni CAGR liczby przedsiębiorstw z branży gastronomicznej i mobilnej gastronomii [%]": (
        "Srednie tempo wzrostu liczby firm w ostatnich 5 latach; "
        "mierzy dynamike rozwoju sektora."
    ),
    "liczba zatrudnionych w restauracjach i mobilnych punktach gastronomicznych [%]": (
        "Udzial zatrudnionych w gastronomii w strukturze rynku pracy; "
        "sygnalizuje znaczenie sektora uslug."
    ),
    "5-letni CAGR liczby zatrudnionych w restauracjach i mobilnych punktach gastronomicznych [%]": (
        "Srednie tempo wzrostu zatrudnienia w gastronomii w ostatnich 5 latach; "
        "pokazuje zmiany popytu na prace w sektorze."
    ),
    "Całkowita liczba chronionych produktów regionalnych i tradycyjnych": (
        "Liczba produktow z ochrona regionalna lub tradycyjna; "
        "odzwierciedla kapital kulinarny i dziedzictwo."
    ),
    "Wskaźnik nasycenia chronionymi produktami regionalnymi (liczba produktów na 10 mln mieszkańców)": (
        "Liczba chronionych produktow w przeliczeniu na 10 mln mieszkancow; "
        "umozliwia porownywanie krajow o roznej populacji."
    ),
    "Porównywalny wskaźnik poziomu cen dla restauracji i hoteli (średnia UE = 100)": (
        "Wzgledny poziom cen uslug gastronomicznych i hotelowych; "
        "wyzsze wartosci oznaczaja mniejsza dostepnosc cenowa."
    ),
    "Udział noclegów udzielonych w III kwartale (miesiące letnie) w ogólnej liczbie noclegów w roku [%]": (
        "Udzial noclegow w sezonie letnim w calorocznej liczbie noclegow; "
        "mierzy skale sezonowosci ruchu turystycznego."
    ),
    "Liczba restauracji z gwiazdka": (
        "Liczba restauracji z wyroznieniem Michelin; "
        "sygnalizuje prestiz i jakosc oferty."
    ),
    "Wskaźnik nasycenia restauracjami z gwiazdkami Michelin (liczba wyróżnionych restauracji na 10 mln mieszkańców)": (
        "Liczba restauracji Michelin na 10 mln mieszkancow; "
        "porownuje intensywnosc oferty premium miedzy krajami."
    ),
}

VARIABLE_IMPUTATION = {
    "liczba przedsiębiorstw z branży gastronomicznej i mobilnej gastronomii": {
        "method": "Srednia",
        "countries": "Austria, Szwecja",
    },
    "5-letni CAGR liczby przedsiębiorstw z branży gastronomicznej i mobilnej gastronomii [%]": {
        "method": "Srednia",
        "countries": "Austria, Szwecja",
    },
    "liczba zatrudnionych w restauracjach i mobilnych punktach gastronomicznych [%]": {
        "method": "Mediana",
        "countries": "Czechy, Portugalia",
    },
    "5-letni CAGR liczby zatrudnionych w restauracjach i mobilnych punktach gastronomicznych [%]": {
        "method": "Srednia",
        "countries": "Czechy, Portugalia",
    },
}


def get_variable_description(name: str) -> str:
    return VARIABLE_DESCRIPTIONS.get(name, "Brak opisu w pliku opisy_zmiennych.py.")


def get_imputation_note(name: str) -> str:
    entry = VARIABLE_IMPUTATION.get(name)
    if not entry:
        return ""
    return f"Uzupelniono braki: Metoda: {entry['method']}; Panstwa: {entry['countries']}."
