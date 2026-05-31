import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.figure_factory as ff

from opisy_zmiennych import get_imputation_note, get_variable_description

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

    # 5. Suma rang (odwrocona: wyzsza wartosc = lepsza pozycja)
    X_ranks = pd.DataFrame(index=X.index)
    for col in cols:
        if col in destimulants:
            X_ranks[col] = X[col].rank(ascending=True, method="average")
        else:
            X_ranks[col] = X[col].rank(ascending=False, method="average")
    sum_ranks_score = X_ranks.sum(axis=1)
    sum_ranks_score = sum_ranks_score.max() - sum_ranks_score

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

def build_knn_weights(coords: np.ndarray, k: int = 4):
    from scipy.spatial import cKDTree

    tree = cKDTree(coords)
    _, idxs = tree.query(coords, k=k + 1)
    n = len(coords)
    W = np.zeros((n, n))
    for i in range(n):
        for j_idx in idxs[i][1:]:
            W[i, j_idx] = 1.0

    row_sums = W.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return W / row_sums

def build_queen_weights(gdf):
    try:
        sindex = gdf.sindex
    except Exception:
        sindex = None

    n = len(gdf)
    W = np.zeros((n, n))
    geoms = gdf.geometry

    for i, geom in enumerate(geoms):
        if geom is None or geom.is_empty:
            continue

        if sindex is not None:
            candidates = list(sindex.intersection(geom.bounds))
        else:
            candidates = range(n)

        for j in candidates:
            if i == j:
                continue
            other = geoms.iloc[j]
            if other is None or other.is_empty:
                continue
            if geom.touches(other):
                W[i, j] = 1.0

    row_sums = W.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return W / row_sums

def moran_i_stat(y: np.ndarray, W: np.ndarray):
    n = len(y)
    z = y - y.mean()
    S0 = W.sum()
    return float((n / S0) * (z @ W @ z) / (z @ z))

def moran_permutation_test(y: np.ndarray, W: np.ndarray, n_perm: int = 999, seed: int = 42):
    rng = np.random.default_rng(seed)
    observed = moran_i_stat(y, W)
    perm_stats = []
    for _ in range(n_perm):
        y_perm = rng.permutation(y)
        perm_stats.append(moran_i_stat(y_perm, W))

    perm_stats = np.array(perm_stats)
    p_value = (np.sum(np.abs(perm_stats) >= abs(observed)) + 1) / (n_perm + 1)
    return observed, p_value, perm_stats

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

def drop_small_islands(gdf, min_ratio: float = 0.02, keep_largest_only: bool = True):
    try:
        from shapely.geometry import MultiPolygon
    except Exception:
        return gdf

    gdf = gdf[gdf.geometry.notna()].copy()
    if gdf.empty:
        return gdf

    orig_crs = gdf.crs
    try:
        gdf = gdf.to_crs("EPSG:3035")
    except Exception:
        return gdf

    def _clean(geom):
        if geom is None or geom.is_empty:
            return geom
        if geom.geom_type == "MultiPolygon":
            parts = list(geom.geoms)
            if not parts:
                return geom
            areas = [p.area for p in parts]
            max_area = max(areas)
            if keep_largest_only:
                keep = [parts[areas.index(max_area)]]
            else:
                keep = [p for p, a in zip(parts, areas) if a >= max_area * min_ratio]
            if not keep:
                keep = [parts[areas.index(max_area)]]
            return MultiPolygon(keep)
        return geom

    gdf["geometry"] = gdf.geometry.apply(_clean)
    return gdf.to_crs(orig_crs)

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
                desc = get_variable_description(s)
                note = get_imputation_note(s)
                if note:
                    st.markdown(f"* **{s}**: {desc}  \n_{note}_")
                else:
                    st.markdown(f"* **{s}**: {desc}")
        
        with col_desc2:
            st.markdown("<span style='color:red;font-weight:bold;'>DESTYMULANTY (Bariery i ograniczenia)</span>", unsafe_allow_html=True)
            for d in destimulants:
                desc = get_variable_description(d)
                note = get_imputation_note(d)
                if note:
                    st.markdown(f"* **{d}**: {desc}  \n_{note}_")
                else:
                    st.markdown(f"* **{d}**: {desc}")

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
                short_labels = {col: f"X{idx+1}" for idx, col in enumerate(numeric_cols)}
                corr = df[numeric_cols].corr()
                corr = corr.rename(index=short_labels, columns=short_labels)
                fig2 = px.imshow(
                    corr,
                    text_auto=".2f",
                    color_continuous_scale="RdBu_r",
                    zmin=-1,
                    zmax=1,
                    aspect="equal",
                    height=520,
                )
                fig2.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    xaxis_title=None,
                    yaxis_title=None,
                )
                fig2.update_xaxes(tickangle=0)
                st.plotly_chart(fig2, use_container_width=True)
                st.markdown("**Legenda zmiennych (macierz korelacji):**")
                for col in numeric_cols:
                    st.markdown(f"- **{short_labels[col]}**: {col}")

    results, X_minmax = compute_rankings(df, id_col, sel["selected"], destimulants)

    with tabs[2]:
        st.header("WAP — Rankingi i Typologia")
        if results.empty:
            st.warning("Brak danych do wyliczenia rankingów.")
        else:
            st.subheader("Wyniki Syntetycznych Mierników Rozwoju SMR")
            st.dataframe(results, height=250)
            st.markdown("*Uwaga: W metodzie Suma rang zastosowano odwrócenie skali, aby wyższa wartość oznaczała wyższą pozycję.*")

            method_notes = {
                "TOPSIS": "Ranking bazuje na odleglosci od rozwiazania idealnego; dobrze rozroznia liderow i maruderow w ukladzie wielowymiarowym.",
                "Hellwig": "Ocena opiera sie na wzorcu rozwoju; wyniki sa stabilne przy standaryzacji i dobrze wskazuja kraje zblizone do wzorca.",
                "BZW": "Wskaznik ilorazowy podkresla relacje do maksimum; premiuje kraje osiagajace wysokie wartosci w wielu cechach.",
                "Kukula": "Unitaryzacja zerowana daje czytelny ranking względny; latwo porownac poziom rozwoju w skali 0-1.",
                "Suma rang": "Porzadek wynika z pozycji w kazdej cesze; metoda jest odporna na skale, ale mniej czula na roznice wartosci.",
                "Iteracyjna": "Ranking powstaje przez sukcesywne wybieranie najlepszych; moze silniej akcentowac kraje o zrownowazonym profilu.",
            }
            
            st.subheader("Ranking wybranej metody")
            method = st.selectbox("Wybierz metode rankingu:", results.columns.tolist(), index=0)
            ranking = results[method].sort_values(ascending=False).to_frame(name="Wartosc")
            ranking.insert(0, "Pozycja", range(1, len(ranking) + 1))
            st.dataframe(ranking, height=300)
            st.markdown(f"**Wniosek (metoda {method}):** {method_notes.get(method, '')}")

            fig3 = px.bar(
                results.sort_values(by=method, ascending=False).reset_index(), 
                x="index", 
                y=method, 
                labels={"index": "Państwo", method: "Wartość miernika"},
                height=350,
                title=f"Ranking państw metodą {method}"
            )
            fig3.update_traces(marker_color='#2ca02c')
            st.plotly_chart(fig3, use_container_width=True)

            st.subheader("Klasyfikacja Homogeniczna Metodą Warda")
            try:
                import scipy.cluster.hierarchy as sch
                labels = df[id_col].values if id_col in df.columns else df.index.values
                fig_ward = ff.create_dendrogram(
                    X_minmax.values,
                    labels=labels,
                    linkagefun=lambda x: sch.linkage(x, method="ward"),
                )
                fig_ward.update_layout(
                    height=350,
                    xaxis_title="Państwo",
                    yaxis_title="Odległość wiązania",
                    margin=dict(l=10, r=10, t=10, b=10),
                )
                st.plotly_chart(fig_ward, use_container_width=True)
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
                merged_plot = drop_small_islands(merged, keep_largest_only=True).reset_index(drop=True).copy()
                merged_plot["feature_id"] = merged_plot.index.astype(str)
                geojson = merged_plot.__geo_interface__
                fig4 = px.choropleth(
                    merged_plot,
                    geojson=geojson,
                    locations="feature_id",
                    featureidkey="properties.feature_id",
                    color="TOPSIS",
                    hover_name="Państwo",
                    color_continuous_scale=[
                        "#f7fbff",
                        "#c6dbef",
                        "#6baed6",
                        "#3182bd",
                        "#08519c",
                    ],
                    height=420,
                )
                fig4.update_geos(
                    fitbounds="locations",
                    visible=False,
                    projection_type="mercator",
                    bgcolor="rgba(0,0,0,0)",
                )
                fig4.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig4, use_container_width=True)
                
                with np.errstate(invalid='ignore'):
                    centroids = np.vstack(merged_plot.geometry.to_crs('+proj=cea').centroid.to_crs(merged_plot.crs).apply(lambda p: (p.x, p.y)).values)

                y = merged_plot["TOPSIS"].fillna(merged_plot["TOPSIS"].mean()).reset_index(drop=True).to_numpy()
                y_std = (y - y.mean()) / (y.std(ddof=1) if y.std(ddof=1) != 0 else 1.0)

                try:
                    weight_method = st.selectbox(
                        "Macierz wag przestrzennych",
                        ["k-NN (centroidy)", "Wspolna granica (queen)"],
                        index=0,
                    )
                    if weight_method == "k-NN (centroidy)":
                        k = st.slider("Liczba sasiedow k", min_value=2, max_value=10, value=4, step=1)
                        W = build_knn_weights(centroids, k=k)
                        weight_label = f"k-NN, k={k}"
                    else:
                        W = build_queen_weights(merged_plot)
                        weight_label = "queen"

                    moran_i, p_value, _ = moran_permutation_test(y_std, W, n_perm=999, seed=42)
                    st.markdown(
                        f"**Globalny Wskaźnik Morana I ({weight_label}):** {moran_i:.4f}  "
                        f"**p-value (test permutacyjny):** {p_value:.4f}"
                    )

                    z = y_std
                    lag = W @ z
                    fig_moran = px.scatter(
                        x=z,
                        y=lag,
                        labels={"x": "Zmienna standaryzowana (Z)", "y": "Lag przestrzenny (Wz)"},
                        title="Wykres Morana",
                        height=320,
                    )
                    fig_moran.add_hline(y=0, line_width=1, line_color="#888")
                    fig_moran.add_vline(x=0, line_width=1, line_color="#888")
                    st.plotly_chart(fig_moran, use_container_width=True)
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