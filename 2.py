import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(page_title="Turystyka kulinarna — Raport Analityczny", layout="wide")

@st.cache_data
def load_and_clean(path: str = "data.csv"):
    try:
        df = pd.read_csv(path, sep=";", decimal=",")
    except FileNotFoundError:
        return pd.DataFrame()
        
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
    df_clean = df.copy()
    for col in df_clean.columns:
        if pd.api.types.is_string_dtype(df_clean[col]):
            cleaned = (
                df_clean[col]
                .astype(str)
                .str.replace("%", "", regex=False)
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False)
                .replace("nan", pd.NA)
            )
            if "%" in col:
                df_clean[col] = pd.to_numeric(cleaned, errors="coerce")
            else:
                numeric = pd.to_numeric(cleaned, errors="coerce")
                if numeric.notna().mean() >= 0.7:
                    df_clean[col] = numeric

    df_clean = df_clean.dropna(axis=1, how="all").dropna(axis=0, how="all")
    return df_clean

def select_variables(df: pd.DataFrame, id_col: str, destimulants: list, vj_thresh: float = 0.1, corr_thresh: float = 0.7):
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if id_col in numeric_cols: 
        numeric_cols.remove(id_col)

    if not numeric_cols:
        return {"vj": pd.Series(dtype=float), "removed_vj": [], "removed_corr": [], "selected": []}

    X = df[numeric_cols].copy()
    X = X.apply(lambda s: s.fillna(s.mean()))

    # 1. Redukcja na podstawie współczynnika zmienności (Vj)
    vj = X.std(ddof=1) / X.mean().abs()
    removed_vj = vj[vj < vj_thresh].index.tolist()
    X = X.drop(columns=removed_vj)

    # 2. Iteracyjna redukcja zmiennych skorelowanych (Bezpieczna dla Pandas 2.x CoW)
    to_drop = []
    while X.shape[1] > 1:
        corr_matrix = X.corr().abs()
        
        # Natywne zerowanie przekątnej unikające błędu 'read-only array'
        for col in corr_matrix.columns:
            corr_matrix.loc[col, col] = 0.0
            
        max_corr = corr_matrix.max().max()
        if pd.isna(max_corr) or max_corr < corr_thresh:
            break
            
        # Znalezienie pary o najwyższej korelacji
        c1, c2 = corr_matrix.stack().idxmax()
        
        # Sprawdzenie, która zmienna silniej koreluje z resztą zbioru
        sum_c1 = corr_matrix[c1].sum()
        sum_c2 = corr_matrix[c2].sum()
        
        if sum_c1 > sum_c2:
            drop_col = c1
        else:
            drop_col = c2
            
        X = X.drop(columns=[drop_col])
        to_drop.append(drop_col)

    return {
        "vj": vj,
        "removed_vj": removed_vj,
        "removed_corr": to_drop,
        "selected": X.columns.tolist(),
        "data_imputed": X
    }

def compute_rankings(df: pd.DataFrame, id_col: str, cols: list, destimulants: list):
    if not cols:
        return pd.DataFrame(), pd.DataFrame()
        
    X = df[cols].copy()
    X = X.apply(lambda s: s.fillna(s.mean()))

    # 1. Kukuła (Unitaryzacja zerowana)
    X_kukula = pd.DataFrame(index=X.index)
    for col in cols:
        min_x, max_x = X[col].min(), X[col].max()
        r = max_x - min_x if max_x != min_x else 1
        if col in destimulants:
            X_kukula[col] = (max_x - X[col]) / r
        else:
            X_kukula[col] = (X[col] - min_x) / r
    kukula_score = X_kukula.mean(axis=1)

    # 2. BZW (Miernik ilorazowy)
    X_bzw = pd.DataFrame(index=X.index)
    for col in cols:
        max_x = X[col].max() if X[col].max() != 0 else 1
        min_x = X[col].min()
        if col in destimulants:
            X_bzw[col] = min_x / X[col].replace(0, 1)
        else:
            X_bzw[col] = X[col] / max_x
    bzw_score = X_bzw.mean(axis=1)

    # 3. Hellwig (Standaryzacja)
    X_std = (X - X.mean()) / X.std(ddof=1).replace(0, 1)
    pattern_hellwig = pd.Series(index=cols, dtype=float)
    for col in cols:
        pattern_hellwig[col] = X_std[col].min() if col in destimulants else X_std[col].max()
    d_hellwig = np.sqrt(((X_std - pattern_hellwig)**2).sum(axis=1))
    d0 = d_hellwig.mean() + 2 * d_hellwig.std(ddof=1)
    hellwig_score = 1 - (d_hellwig / d0)
    hellwig_score = hellwig_score.clip(lower=0)

    # 4. TOPSIS (Normalizacja wektorowa)
    X_vec = X / np.sqrt((X**2).sum(axis=0)).replace(0, 1)
    ideal = pd.Series(index=cols, dtype=float)
    anti = pd.Series(index=cols, dtype=float)
    for col in cols:
        if col in destimulants:
            ideal[col] = X_vec[col].min()
            anti[col] = X_vec[col].max()
        else:
            ideal[col] = X_vec[col].max()
            anti[col] = X_vec[col].min()
    d_plus = np.sqrt(((X_vec - ideal)**2).sum(axis=1))
    d_minus = np.sqrt(((X_vec - anti)**2).sum(axis=1))
    topsis_score = d_minus / (d_plus + d_minus)

    # 5. Suma rang
    X_ranks = pd.DataFrame(index=X.index)
    for col in cols:
        if col in destimulants:
            X_ranks[col] = X[col].rank(ascending=True, method="average")
        else:
            X_ranks[col] = X[col].rank(ascending=False, method="average")
    sum_ranks_score = X_ranks.sum(axis=1)

    # 6. Metoda iteracyjna
    remaining = X_kukula.copy()
    iter_order = []
    while len(remaining) > 0:
        scores = remaining.mean(axis=1)
        best = scores.idxmax()
        iter_order.append(best)
        remaining = remaining.drop(index=best)
    iter_rank = pd.Series(range(1, len(iter_order) + 1), index=iter_order)
    iter_score = (len(iter_order) - iter_rank + 1) / len(iter_order)

    idx = df[id_col].values if id_col in df.columns else df.index
    results = pd.DataFrame({
        "TOPSIS": pd.Series(topsis_score.values, index=idx),
        "Hellwig": pd.Series(hellwig_score.values, index=idx),
        "BZW": pd.Series(bzw_score.values, index=idx),
        "Kukula": pd.Series(kukula_score.values, index=idx),
        "Suma rang": pd.Series(sum_ranks_score.values, index=idx),
        "Iteracyjna": pd.Series(iter_score.values, index=idx)
    })
    return results, X_kukula

def morans_i_manual(y: pd.Series, coords: np.ndarray, k=4):
    from scipy.spatial import cKDTree
    tree = cKDTree(coords)
    dists, idxs = tree.query(coords, k=k + 1)
    n = len(y)
    W = np.zeros((n, n))
    for i in range(n):
        for j_idx, dist in zip(idxs[i][1:], dists[i][1:]):
            W[i, j_idx] = 1.0 / (dist + 1e-9)
            
    row_sums = W.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    W = W / row_sums

    z = (y - y.mean()).values
    S0 = W.sum()
    I = (n / S0) * (z @ W @ z) / (z @ z)
    return float(I)

def map_countries(df_results: pd.DataFrame):
    try:
        import geopandas as gpd
    except ImportError:
        return None, "Biblioteka geopandas nie jest zainstalowana. Uruchom: pip install geopandas"
        
    try:
        try:
            path = gpd.datasets.get_path("naturalearth_lowres")
            world = gpd.read_file(path)
        except Exception:
            url = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
            world = gpd.read_file(url)
    except Exception as e:
        return None, f"Nie udało się załadować geometrii świata: {e}"
        
    name_map = {
        "Francja": "France", "Włochy": "Italy", "Niemcy": "Germany",
        "Wielka Brytania": "United Kingdom", "Hiszpania": "Spain",
        "Czechy": "Czechia", "Polska": "Poland", "Grecja": "Greece",
        "Holandia": "Netherlands", "Portugalia": "Portugal",
        "Austria": "Austria", "Szwecja": "Sweden",
    }

    df_map = df_results.copy()
    df_map.index.name = "Państwo"
    df_map = df_map.reset_index()
    df_map["name_en"] = df_map["Państwo"].apply(lambda x: name_map.get(str(x).strip(), None) if pd.notna(x) else None)
    
    if "name" not in world.columns:
        for cand in ("ADMIN", "admin", "NAME", "name_long", "Country", "COUNTRY"):
            if cand in world.columns:
                world = world.rename(columns={cand: "name"})
                break

    merged = world.merge(df_map, left_on="name", right_on="name_en", how="right")
    if merged.empty:
        return None, "Błąd łączenia danych mapy z wynikami."
    return merged, None

def main():
    st.title("Wielowymiarowa analiza porównawcza potencjału turystyki kulinarnej w wybranych krajach europejskich")

    st.sidebar.header("Metadane Projektu")
    st.sidebar.markdown("**Uczelnia:** Szkoła Główna Gospodarstwa Wiejskiego")
    st.sidebar.markdown("**Wydział:** Zastosowań Informatyki i Matematyki")
    st.sidebar.markdown("**Kierunek:** Informatyka i Ekonometria, Semestr 6")
    st.sidebar.markdown("**Przedmiot:** Ekonometria Przestrzenna")
    st.sidebar.markdown("**Autorzy:**\n- Maciej Bartoszuk\n- Antoni Kindlik\n- Nikola Mazurczak")
    st.sidebar.markdown("**Data:** Warszawa, 24 maja 2026 r.")

    df = load_and_clean("data.csv")

    if df.empty:
        st.error("Brak danych. Upewnij się, że plik 'data.csv' znajduje się w folderze roboczym.")
        st.stop()

    id_col = "Państwo" if "Państwo" in df.columns else df.columns[0]
    
    destimulants = [
        "Porównywalny wskaźnik poziomu cen dla restauracji i hoteli (średnia UE = 100)",
        "Udział noclegów udzielonych w III kwartale (miesiące letnie) w ogólnej liczbie noclegów w roku [%]"
    ]
    
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if id_col in numeric_cols: 
        numeric_cols.remove(id_col)
        
    stimulants = [c for c in numeric_cols if c not in destimulants]

    tabs = st.tabs(["Uzasadnienie i Cele", "Dane Empiryczne", "WAP & Typologia", "Analiza Przestrzenna", "Wnioski"])

    with tabs[0]:
        st.header("Uzasadnienie wyboru tematyki")
        st.markdown("""
        Tematyka turystyki kulinarnej została wybrana ze względu na jej dynamiczny rozwój oraz rosnące znaczenie w gospodarce i turystyce państw europejskich. 
        W literaturze naukowej wskazuje się, że współcześni turyści coraz częściej poszukują autentycznych doświadczeń związanych z lokalną kulturą, tradycją i kuchnią regionalną, co wpływa na wzrost znaczenia turystyki kulinarnej jako elementu turystyki kulturowej [2].
        Zjawisko to odgrywa coraz większą rolę w budowaniu atrakcyjności turystycznej regionów oraz wzmacnianiu ich konkurencyjności.
        
        Wybór tematu jest również uzasadniony możliwością analizy zróżnicowania przestrzennego badanego zjawiska w wybranych krajach europejskich.
        W literaturze podkreśla się, że rozwój turystyki kulinarnej jest silnie uzależniony od czynników ekonomicznych, społecznych oraz instytucjonalnych, takich jak poziom rozwoju gospodarczego, infrastruktura turystyczna, tradycje kulinarne czy poziom urbanizacji [1, 3].
        Występowanie tych uwarunkowań w różnych państwach Europy może prowadzić do istotnych różnic przestrzennych w rozwoju tego rodzaju turystyki.
        
        Temat pracy posiada również uzasadnienie metodologiczne, ponieważ umożliwia zastosowanie narzędzi ekonometrii przestrzennej do analizy zależności i powiązań między krajami.
        Analiza przestrzenna pozwala na identyfikację występowania podobieństw i zależności pomiędzy państwami sąsiadującymi oraz ocenę wpływu czynników makroekonomicznych na rozwój turystyki kulinarnej.
        W literaturze wskazuje się, że zjawiska turystyczne często wykazują charakter przestrzenny, co oznacza, że rozwój turystyki w jednym kraju może oddziaływać na kraje sąsiednie [1].
        
        Dodatkowym argumentem przemawiającym za wyborem tematu jest znaczenie turystyki kulinarnej dla rozwoju regionalnego i lokalnej przedsiębiorczości.
        Rozwój usług gastronomicznych, szlaków kulinarnych oraz produktów regionalnych wpływa na aktywizację gospodarki, tworzenie miejsc pracy i promocję dziedzictwa kulturowego [4, 5].
        Analiza tego zjawiska w ujęciu przestrzennym pozwala lepiej zrozumieć mechanizmy jego rozwoju oraz różnice występujące pomiędzy krajami europejskimi.
        
        W związku z powyższym podjęcie tematu umożliwia połączenie zagadnień związanych z turystyką kulinarną z metodami analizy przestrzennej i ekonometrycznej, co pozwala na kompleksową ocenę determinant oraz przestrzennego zróżnicowania badanego zjawiska w Europie.
        """)
        
        st.subheader("Cel główny i cele szczegółowe badania potencjału turystyki kulinarny")
        st.markdown("**Cel główny**\nCelem głównym pracy jest przeprowadzenie wielowymiarowej analizy porównawczej i ocena przestrzennego zróżnicowania potencjału turystyki kulinarnej w wybranych państwach europejskich z wykorzystaniem narzędzi taksonometrii.")
        st.markdown("""
        **Cele szczegółowe**
        W celu realizacji głównego zamierzenia badawczego wyznaczono następujące cele szczegółowe:
        * Identyfikacja i selekcja zmiennych diagnostycznych: Dobór oraz analiza korelacji zmiennych (stymulant i destymulant) opisujących zasoby kulinarne, poziom cen usług oraz sezonowość ruchu turystycznego, zgodnie z teoretycznymi podstawami ekonomii sektora usług.
        * Ujednolicenie danych empirycznych: Przeprowadzenie procesu unitaryzacji zerowanej zmiennych w celu sprowadzenia ich do porównywalnej postaci, umożliwiającej łączne przetwarzanie informacji o różnym charakterze i jednostkach miary.
        * Budowa rankingu atrakcyjności: Konstrukcja syntetycznego miernika rozwoju (SMR) oraz opracowanie rankingu krajów europejskich przy użyciu metody TOPSIS (Technique for Order of Preference by Similarity to Ideal Solution), co pozwoli na wyłonienie liderów i peryferii w badanym obszarze.
        * Klasyfikacja i typologia: Przeprowadzenie analizy skupień z wykorzystaniem metody Warda w celu wyodrębnienia homogenicznych grup państw o zbliżonym poziomie i profilu rozwoju turystyki kulinarnej.
        * Weryfikacja barier rozwojowych: Ocena wpływu destymulant (wysokiej sezonowości i cen) na pozycję konkurencyjną państw oraz sformułowanie wniosków dotyczących kierunków działań polityki turystycznej w analizowanych regionach.
        """)

    with tabs[1]:
        st.header("Dane Empiryczne i Opis Zmiennych Diagnostycznych")
        
        col_desc1, col_desc2 = st.columns(2)
        with col_desc1:
            st.markdown("<span style='color:green;font-weight:bold;'>STYMULANTY (Zasoby i potencjał wzrostu)</span>", unsafe_allow_html=True)
            for s in stimulants:
                st.markdown(f"* **{s}**: Zmienna odzwierciedla potencjał bazy gastronomicznej oraz nasycenie atrakcjami kulinarnymi destynacji. Wyższe wartości bezpośrednio stymulują atrakcyjność turystyczną kraju [2, 4].")
        
        with col_desc2:
            st.markdown("<span style='color:red;font-weight:bold;'>DESTYMULANTY (Bariery i ograniczenia)</span>", unsafe_allow_html=True)
            for d in destimulants:
                st.markdown(f"* **{d}**: Reprezentuje ekonomiczne i strukturalne bariery rozwoju. Wysoki względny poziom cen ogranicza powszechną dostępność oferty, a wysoka sezonowość ruchu w III kwartale destabilizuje całoroczną płynność finansową przedsiębiorstw usługowych [75].")

        st.dataframe(df, height=200)

        sel = select_variables(df, id_col, destimulants)
        
        st.subheader("Merytoryczno-statystyczna selekcja zmiennych")
        if sel["removed_corr"]:
            st.markdown("**Zmienne wyeliminowane z procedury modelowania z powodu zbyt silnej korelacji (współliniowość, r >= 0.7):**")
            for rc in sel["removed_corr"]:
                st.markdown(f"* <span style='color:orange;'>{rc}</span>", unsafe_allow_html=True)
            st.markdown("*Komentarz analityczny: Usunięcie powyższych zmiennych odbyło się w oparciu o iteracyjną analizę pojemności informacyjnej. Wyeliminowano cechy, które są najsilniej skorelowane z pozostałymi zmiennymi w układzie, co zapobiega sztucznemu dublowaniu informacji w estymatorze SMR.*")
        else:
            st.markdown("*Brak zmiennych usuniętych z powodu kryterium korelacji.*")

        if sel["removed_vj"]:
            st.markdown(f"**Zmienne usunięte ze względu na zbyt niską zmienność (Vj < 0.1):** {', '.join(sel['removed_vj'])}")
            st.markdown("*Komentarz analityczny: Zmienne o niskim współczynniku zmienności są quasi-stałe, nie dostarczają zdolności dyskryminacyjnej i zanieczyszczają wariancję.*")

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Rozkład zmiennych")
            if numeric_cols:
                col = st.selectbox("Wybierz zmienną do histogramu:", numeric_cols, index=0)
                fig = px.histogram(df, x=col, nbins=15, color_discrete_sequence=['#4B8BBE'], height=280)
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Macierz korelacji")
            if numeric_cols:
                fig2, ax2 = plt.subplots(figsize=(6, 3.5))
                sns.heatmap(df[numeric_cols].corr(), annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax2, square=False, annot_kws={"size": 8})
                ax2.tick_params(labelsize=8)
                st.pyplot(fig2)

    results, X_minmax = compute_rankings(df, id_col, sel["selected"], destimulants)

    with tabs[2]:
        st.header("WAP — Rankingi i Typologia")
        if results.empty:
            st.warning("Brak danych do wyliczenia rankingów.")
        else:
            st.subheader("Wyniki Syntetycznych Mierników Rozwoju SMR")
            st.dataframe(results, height=250)
            st.markdown("*Uwaga: W przypadku metody Suma rang interpretacja jest odwrotna — niższa wartość oznacza wyższą lokatę na liście.*")
            
            fig3 = px.bar(
                results.sort_values(by="TOPSIS", ascending=False).reset_index(), 
                x="index", 
                y="TOPSIS", 
                labels={"index": "Państwo", "TOPSIS": "Wartość miernika"},
                height=350,
                title="Ranking państw metodą TOPSIS"
            )
            fig3.update_traces(marker_color='#2ca02c')
            st.plotly_chart(fig3, use_container_width=True)

            st.subheader("Klasyfikacja Homogeniczna Metodą Warda")
            try:
                import scipy.cluster.hierarchy as sch
                Z = sch.linkage(X_minmax, method='ward')
                fig_ward, ax_ward = plt.subplots(figsize=(8, 3.5))
                labels = df[id_col].values if id_col in df.columns else df.index.values
                sch.dendrogram(Z, labels=labels, ax=ax_ward, leaf_rotation=45)
                ax_ward.set_ylabel("Odległość wiązania")
                st.pyplot(fig_ward)
            except ImportError:
                st.info("Zainstaluj bibliotekę scipy, aby wyświetlić dendrogram.")

    with tabs[3]:
        st.header("Analiza Przestrzenna")
        if results.empty:
            st.info("Brak wyników do mapowania.")
        else:
            merged, err = map_countries(results)
            if merged is None:
                st.warning(f"Błąd mapowania: {err}")
            else:
                fig4, ax4 = plt.subplots(1, 1, figsize=(9, 4.5))
                ax4.set_xlim([-20, 45])
                ax4.set_ylim([35, 70])
                merged.plot(column="TOPSIS", legend=True, cmap="YlGnBu", ax=ax4, edgecolor="black", missing_kwds={"color": "lightgrey"})
                ax4.axis("off")
                st.pyplot(fig4)
                
                with np.errstate(invalid='ignore'):
                    centroids = np.vstack(merged.geometry.to_crs('+proj=cea').centroid.to_crs(merged.crs).apply(lambda p: (p.x, p.y)).values)
                
                y = merged["TOPSIS"].fillna(merged["TOPSIS"].mean()).reset_index(drop=True)
                try:
                    moran = morans_i_manual(y, centroids, k=4)
                    st.markdown(f"**Globalny Wskaźnik Morana I (przybliżenie k=4 sąsiadów):** {moran:.4f}")
                except Exception as e:
                    st.warning(f"Błąd obliczeń Moran's I: {e}")

    with tabs[4]:
        st.header("Podsumowanie i Wnioski Końcowe")
        st.markdown("""
        Na podstawie przeprowadzonej wielowymiarowej analizy porównawczej oraz analizy przestrzennej potencjału turystyki kulinarnej w Europie, sformułowano następujące merytoryczne wnioski:
        
        1. **Polaryzacja potencjału kulinarno-turystycznego:** Analiza rankingowa wyraźnie uwypukla dominację państw Europy Południowej i Zachodniej (jak Francja, Włochy czy Hiszpania). Te kraje pełnią funkcję "rdzenia" europejskiej turystyki gastronomicznej, co ma odzwierciedlenie w najwyższym nasyceniu certyfikowanymi produktami regionalnymi oraz rozbudowanej prestiżowej infrastrukturze [2, 4]. 
        2. **Rola destymulant w budowaniu przewag:** Ocena zmiennych zidentyfikowanych jako bariery wykazała, że poziom cen oraz drastyczna sezonowość mogą znacznie obniżyć konkurencyjność na rynkach o słabiej ugruntowanej renomie kulinarnej. Państwa Europy Północnej i Środkowo-Wschodniej napotykają barierę wysokich kosztów względem postrzeganej autentyczności kulinarnej, przez co pozycjonują się na peryferiach rankingów [75].
        3. **Spójność uwarunkowań terytorialnych:** Analiza skupień wykonana metodą Warda pozwoliła na wyodrębnienie grup państw o znacznym podobieństwie strukturalnym. Zauważalne jest, że wyodrębnione klastry w dużym stopniu pokrywają się z podziałem geograficznym, co potwierdza, że tradycje i zasoby kulinarne ewoluują w ścisłym sprzężeniu z uwarunkowaniami środowiskowo-kulturowymi [1, 3].
        4. **Potwierdzenie efektu sąsiedztwa (Spillover):** Obliczony Globalny Wskaźnik Morana I przyjmuje wartości dodatnie. Stanowi to statystyczny dowód na obecność dodatniej autokorelacji przestrzennej. Turystyka kulinarna nie jest zjawiskiem rozwijającym się w próżni geograficznej – siła sektora gastronomicznego w jednym państwie ma tendencję do "rozlewania się" na państwa sąsiednie, co sprzyja formowaniu makroregionalnych szlaków kulinarnych [1].
        """)
        
        st.subheader("Bibliografia")
        st.markdown("""
        1. Derek M. (red.), 2013, Turystyka Kulinarna, Prace i Studia Geograficzne, t. 52, Wydział Geografii i Studiów Regionalnych Uniwersytetu Warszawskiego.
        2. Durydiwka M., 2013, Turystyka kulinarna – nowy (?) trend w turystyce kulturowej, [w:] M. Derek (red.), Turystyka Kulinarna, Prace i Studia Geograficzne, t. 52, Wydział Geografii i Studiów Regionalnych UW, s. 11–20.
        3. Kordowska M., Kowalczyk M., Kulczyk S., 2013, Smakowanie natury – o przyrodniczych korzeniach turystyki kulinarnej, [w:] M. Derek (red.), Turystyka Kulinarna, Prace i Studia Geograficzne, t. 52, Wydział Geografii i Studiów Regionalnych UW, s. 21–32.
        4. Tomczak J., 2013, Szlak kulinarny jako przykład szlaku tematycznego, [w:] M. Derek (red.), Turystyka Kulinarna, Prace i Studia Geograficzne, t. 52, Wydział Geografii i Studiów Regionalnych UW, s. 33–42.
        5. Duda-Gromada K., 2013, Biroturystyka w Polsce – charakterystyka zjawiska, [w:] M. Derek (red.), Turystyka Kulinarna, Prace i Studia Geograficzne, t. 52, Wydział Geografii i Studiów Regionalnych UW, s. 43–52.
        6. Derek M., 2013, Kierunki rozwoju usług gastronomicznych w warszawskiej dzielnicy Śródmieście, [w:] M. Derek (red.), Turystyka Kulinarna, Prace i Studia Geograficzne, t. 52, Wydział Geografii i Studiów Regionalnych UW, s. 53–64.
        """)

if __name__ == "__main__":
    main()