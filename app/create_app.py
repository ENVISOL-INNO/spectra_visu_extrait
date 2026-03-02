import json
import os
import pathlib
import numpy as np
import pandas as pd
import time
import regex as re  # Type : ignore
import plotly  # type: ignore
import plotly.graph_objects as go  # type: ignore
from plotly.colors import qualitative

from py_ce_forms_api import CeFormsClient, AssetElt


from trias_py import (
    TriasDrillingViz,
    TriasSensorData,
    TriasMethod,
    TriasSpectralViz,
    TriasProject,
    TriasAnalysis,
    TriasMethodFactory,
    TriasProcessing,
    TriasProject,
)

### Pour format_data

class Spectra:
    """_summary_"""

    def __init__(self, spectra_dict: dict, id:str | None = None) -> None:
        """
        spectra looks like this:
        {
            "spectroscopy": spectro,
            "sample_name": sample_name,
            "bands": [wavelengths],
            "spectra": [values]
        }
        """
        self.spectroscopy: str = spectra_dict["spectroscopy"]
        self.sample_name: str = spectra_dict["sample_name"]
        self.bands: list[float] = spectra_dict["bands"]
        self.spectra: list[float] = spectra_dict["spectra"]
        self.metadata: list[float] = spectra_dict["metadata"]
        self.id: None | str = id

    def from_sensor_data(sensor_data: TriasSensorData):
        """
        Constructor of Spectra
        """
        asset: AssetElt = sensor_data.get_data()
        return Spectra(json.loads(asset.get_bytes().decode("utf-8")), sensor_data.get_id())

### Pour main_execute

class SpectroVisualization:
    def init_spec(self, spectro: str):
        self._spec_viz = {
                "TPH": {"color": "red", 
                    "ranges": [
                        [1345, 1495], 
                        [2785, 3025],
                        [4225, 4455]]},
                "Aromatiques": {"color": "green", 
                    "ranges": [ 
                        [805, 835],
                        [865, 895],                  
                        [1510, 1540],
                        [2970, 3150]]},
                "Carbonates": {
                    "color": "yellow",
                    "ranges": [
                        [1435, 1465],
                        [1555, 1585],
                        [1795, 1825],
                        [2485, 2515],
                        [2840, 2900],
                        [2965, 2995]
                    ]
                },
                "Eau": {"color": "blue", 
                    "ranges": [
                        [1640, 1670], 
                        [2135, 2165], 
                        [3395, 3435]]
                },
                "Argiles": {"color": "orange", 
                    "ranges": [
                        [900, 920], 
                        [1230, 1280], 
                        [3550, 3730], 
                        [4480, 4580]]
                },
                "xCO2": {"color": "magenta", 
                    "ranges": [
                        [2350, 2380]]
                },
                "xGaz (eau, acetone)": {"color": "cyan", 
                    "ranges": [
                        [1725, 1755],
                        [1205, 1235]]
                }}

    def add_indicative_bands_plotly(self, fig: plotly.graph_objs.Figure) -> plotly.graph_objs.Figure:
        """
        Ajoute des bandes colorées indicatives (TPH, eau, carbonates, etc.) à une figure Plotly.
        """
        for label, band_info in self._spec_viz.items():
            for band_range in band_info["ranges"]:
                fig.add_shape(
                    type="rect",
                    x0=band_range[0],
                    x1=band_range[1],
                    y0=0,
                    y1=1,
                    xref="x",
                    yref="paper",
                    fillcolor=band_info["color"],
                    opacity=0.3,
                    line_width=0,
                    name=f"{label} Band",
                )
        for label, info in self._spec_viz.items():
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="lines",
                    line=dict(color=info["color"], width=4),
                    name=label,
                )
            )
        return fig



class FigureSpectra(SpectroVisualization):
    def __init__(
        self,
        spectro: str,
        bands: np.ndarray,
        spectra: np.ndarray | None = None,
        sample_names: list[str] | None = None,
        dict_samples: dict[str, dict | str] | None = None
    ):
        """
        Flexible constructor:
        - Si dict_samples est fourni, il est utilisé.
        - Sinon, spectra et sample_names doivent être fournis.
        """
        self.spectro = spectro
        self.bands = bands
        self.spectra = spectra
        self.sample_names = sample_names
        self.dict_samples = dict_samples
        print(209, type(self.bands))
        self.init_spec(spectro)
        print(211)
        self.init_formatting_data()
        print(213)

    def init_formatting_data(self):
        """
        Transforme les entrées en dictionnaire self.data : {sample_name: [replicate1, replicate2, ...]}
        """
        self.data: dict[str, list[np.ndarray]] = {}
        self.tph: dict[str, list[np.ndarray]] = {}

        if self.dict_samples is not None:
            # Ancienne approche avec dict
            
            for key, value in self.dict_samples.items():
                sample_id = value["sample_name"]
                if sample_id not in self.data:
                    self.data[sample_id] = []
                    self.tph[sample_id] = []
                self.data[sample_id].append(value['spectra'])
                if np.array(value["metadata"]["Displayed Prediction"], dtype=float)==-1:
                    self.tph[sample_id].append(None)
                else:
                    self.tph[sample_id].append(np.array(value["metadata"]["Displayed Prediction"], dtype=float))
        elif self.spectra is not None and self.sample_names is not None:
            # Nouvelle approche avec matrice + noms
            for spectrum, name in zip(self.spectra, self.sample_names):
                if name not in self.data:
                    self.data[name] = []
                    self.tph[name] = []
                self.data[name].append(spectrum)
                self.tph[name].append(None)
        else:
            raise ValueError(
                "Il faut fournir soit dict_samples, soit spectra + sample_names."
            )

    def plot_spectra_plotly(
        self, add_bands=False, add_ref_spectra=True
    ) -> dict[str, plotly.graph_objs.Figure]:
        """
        Produit une figure pour chaque échantillon avec des bandes colorées (rouge : TPH, bleu : eau, jaune : carbonates).
        """
        print(254)
        dict_fig: dict = {}
        # Création des figures
        for sample_name, replicates in self.data.items():
            fig = go.Figure()
            print(259, sample_name)
            # Ajouter une ligne verticale à 2926 pour les TPH
            ymin, ymax = np.min(replicates), np.max(replicates)
            fig.add_shape(
                type="line",
                x0=2926,
                x1=2926,
                y0=ymin,
                y1=ymax+1,
                line=dict(color="black", dash="dash"),  # k-- équivalent
            )
            print(270)
            # spectre moyen
            mean_spectrum = np.mean(replicates, axis=0)
            fig.add_trace(
                go.Scatter(
                    x=self.bands,
                    y=mean_spectrum,
                    mode="lines",
                    line=dict(color="red", width=1.3),
                    name="Spectre moyen",
                )
            )
            # Réplicats
            for idx, spectrum in enumerate(replicates):
                fig.add_trace(
                    go.Scatter(
                        x=self.bands,
                        y=spectrum,
                        mode="lines",
                        line=dict(width=0.5),
                        opacity=0.7,
                        name=f"Replicate {idx + 1}",
                    )
                )
            print(294)

            # Charger les bandes spectrales depuis le fichier json
            if add_bands:
                fig = self.add_indicative_bands_plotly(fig)
            print(299)

            tph = np.mean(np.array(self.tph[sample_name], dtype=float))
            tph_std = np.std(np.array(self.tph[sample_name], dtype=float))

            fig.update_layout(
                title = (
                    f"Sample {sample_name}: tph = {tph:.2f} +/- {tph_std:.2f} mg/kg"
                    if tph is not None
                    else f"Sample {sample_name}"
                ),
                xaxis_title="bands (cm⁻¹)",
                yaxis_title="Absorbance",
                xaxis=dict(autorange="reversed"),
                width=1200,
                height=600,
            )
            print(316)

            # ===== AJOUT DES RÉFÉRENCES =====
            # if add_ref_spectra:
            #     base_dir = os.path.dirname(__file__)  # dossier du script
            #     json_path = os.path.join(base_dir, "Ref_spectra.json")

            #     # charger le JSON
            #     with open(json_path, "r") as f:
            #         df_ref = json.load(f)  # liste de dictionnaires
                
            #     x_ref = np.array(df_ref["Bands"])
            #     carb_ref = np.array(df_ref["Carbonates"])
            #     tph_ref = np.array(df_ref["TPH"])
            #     print(327, type(self.bands))
            #     print(327, self.bands)
            #     mask = (self.bands > 2900) & (self.bands < 3100)
            #     print(329)
            #     m = mean_spectrum[mask].mean()
                
            #     fig.add_trace(
            #         go.Scatter(
            #             x=x_ref,
            #             y=carb_ref+m+0.3,
            #             mode="lines",
            #             line=dict(color="dimgray", width=2),
            #             name="Carbonates (référence)",
            #         )
            #     )
            #     fig.add_trace(
            #         go.Scatter(
            #             x=x_ref,
            #             y=tph_ref+m+0.3,
            #             mode="lines",
            #             line=dict(color="black", width=2),
            #             name="TPH (référence)",
            #         )
            #     )
            # print(353)

            dict_fig[sample_name] = fig
        return dict_fig
    
    def plot_all_spectra_plotly(self, add_bands=False, plot_mean_only=True) -> go.Figure:
        """
        Produit une figure avec tous les spectres.
        
        Args:
            add_bands: bool, si True ajoute les bandes indicatives (TPH, eau, carbonates)
            plot_mean_only: bool, si True affiche uniquement le spectre moyen par échantillon
                            si False, affiche tous les réplicats comme avant
        
        Returns:
            fig: plotly.graph_objs.Figure
        """
        fig = go.Figure()
        color_list = qualitative.Plotly  # Liste de couleurs distinctes
        color_cycle = iter(color_list * (len(self.data) // len(color_list) + 1))  # Pour cycler si trop d'échantillons

        all_y_values = []
        for sample_name, replicates in self.data.items():
            color = next(color_cycle)
            if plot_mean_only:
                # Calcul du spectre moyen
                mean_spectrum = np.mean(replicates, axis=0)
                fig.add_trace(
                    go.Scatter(
                        x=self.bands,
                        y=mean_spectrum,
                        mode="lines",
                        line=dict(color=color, width=2),
                        opacity=0.8,
                        name=f"{sample_name} (moyenne)",
                        showlegend=True
                    )
                )
                all_y_values.append(mean_spectrum)
            else:
                # Affichage de tous les réplicats comme avant
                for idx, spectrum in enumerate(replicates):
                    fig.add_trace(
                        go.Scatter(
                            x=self.bands,
                            y=spectrum,
                            mode="lines",
                            line=dict(color=color, width=1),
                            opacity=0.6,
                            name=f"{sample_name} - R{idx+1}",
                            showlegend=(idx == 0),  # N'affiche la légende qu'une fois
                        )
                    )
                    all_y_values.append(spectrum)

        # Ajouter les bandes spectrales si demandé
        if add_bands:
            fig = self.add_indicative_bands_plotly(fig)

        # Ajout d'un trait a 2926cm-1 pour les TPH
        if all_y_values:
            ymin = np.min(all_y_values)
            ymax = np.max(all_y_values)
            fig.add_shape(
                type="line",
                x0=2926,
                x1=2926,
                y0=ymin,
                y1=ymax+1,
                line=dict(color="black", dash="dash"),  # k-- équivalent
            )

        fig.update_layout(
            title="All samples" + (" (moyenne)" if plot_mean_only else ""),
            xaxis_title="bands (cm⁻¹)",
            yaxis_title="Absorbance",
            xaxis=dict(autorange="reversed"),
            legend=dict(itemsizing="constant", font=dict(size=10)),
            width=1200,
            height=600,
        )
        return fig
    
    def spectre_3D(
        self,
        sample_spectra: dict[str, np.ndarray],
        sample_concentration: dict[str, np.ndarray],
        wl_min: float = None,
        wl_max: float = None
    ):
        # Moyennes
        mean_concentrations = np.array([
            np.mean(v) if len(v) > 0 else np.nan
            for v in sample_concentration.values()
        ])
        mean_spectra = np.array([
            np.mean(v, axis=0) if len(v) > 0 else np.full(v.shape[1], np.nan)
            for v in sample_spectra.values()
        ])

        # Tri
        sorted_idx = np.argsort(mean_concentrations)
        mean_concentrations = mean_concentrations[sorted_idx]
        mean_spectra = mean_spectra[sorted_idx]

        # Zoom
        bands = np.array(self.bands)
        if wl_min is not None and wl_max is not None:
            mask = (bands >= wl_min) & (bands <= wl_max)
            bands = bands[mask]
            mean_spectra = mean_spectra[:, mask]

        # Tracés
        WAVELENGTHS, SAMPLES = np.meshgrid(bands, np.arange(mean_spectra.shape[0]))
        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(111, projection='3d')

        surf = ax.plot_surface(WAVELENGTHS, SAMPLES, mean_spectra, cmap='jet', edgecolor='none')
        # cbar = fig.colorbar(surf, ax=ax, shrink=0.6, aspect=15)
        # cbar.set_label("Absorbance", fontsize=14)

        ax.set_xlabel('Wavenumbers (cm⁻¹)', fontsize=16)
        ax.set_ylabel('Samples', fontsize=16)
        ax.set_zlabel('Absorbance', fontsize=16)
        ax.set_xlim(bands.max(), bands.min())
        
        step = max(1, len(mean_concentrations) // 10)
        ax.set_yticks(np.arange(0, len(mean_concentrations), step))
        ax.set_yticklabels([f"{c:.2f}" for c in mean_concentrations[::step]], fontsize=12)
        ax.set_title("Spectres moyens triés par concentration", fontsize=18)

        return fig
    
    def plot_spectra_by_class_plotly(self, classes: np.ndarray, add_bands=False) -> dict[int, go.Figure]:
        """
        Produit une figure Plotly par classe, en regroupant les échantillons appartenant à chaque classe.
        
        Args:
            classes: np.ndarray de taille n_samples avec l'étiquette de classe pour chaque échantillon
            add_bands: bool, si True ajoute les bandes indicatives (TPH, eau, carbonates)
        
        Returns:
            dict_fig: dictionnaire {classe: Figure} avec la figure correspondante à chaque classe
        """
        if self.spectra is None or self.sample_names is None:
            raise ValueError("Pour cette méthode, il faut utiliser l'approche spectra + sample_names.")

        dict_fig: dict[int, go.Figure] = {}
        
        # On construit un dictionnaire classe -> indices des échantillons
        class_indices: dict[int, list[int]] = {}
        for idx, cl in enumerate(classes):
            if cl not in class_indices:
                class_indices[cl] = []
            class_indices[cl].append(idx)
        
        # Création des figures par classe
        for cl, indices in class_indices.items():
            fig = go.Figure()
            for idx in indices:
                spectrum = self.spectra[idx]
                sample_name = self.sample_names[idx]
                fig.add_trace(
                    go.Scatter(
                        x=self.bands,
                        y=spectrum,
                        mode="lines",
                        name=sample_name,
                        opacity=0.7,
                    )
                )
            # Ajouter bandes indicatives si demandé
            if add_bands:
                fig = self.add_indicative_bands_plotly(fig)
            
            fig.update_layout(
                title=f"Class {cl} spectra",
                xaxis_title="bands (cm⁻¹)",
                yaxis_title="Absorbance",
                xaxis=dict(autorange="reversed"),
                width=1200,
                height=600,
            )
            dict_fig[cl] = fig
        print(589, "end plot spectra by class plotly")
        return dict_fig

    def plot_all_samples_vs_others(self, add_bands=False) -> dict[str, go.Figure]:
        """
        Crée un dictionnaire de figures comparant chaque échantillon
        à tous les autres échantillons.

        Args:
            add_bands: bool, si True ajoute les bandes indicatives

        Returns:
            dict_fig: dictionnaire {sample_name: go.Figure}
        """
        print(660)
        dict_fig = {}
        for sample_name in self.data.keys():
            fig = go.Figure()
            color_others = "blue"
            color_sample = "red"

            # --- Spectres moyens des autres échantillons ---
            for other_name, replicates in self.data.items():
                if other_name != sample_name:
                    mean_spectrum = np.mean(replicates, axis=0)
                    fig.add_trace(go.Scatter(
                        x=self.bands,
                        y=mean_spectrum,
                        mode="lines",
                        line=dict(color=color_others, width=2),
                        name=f"{other_name} (moyenne)",
                        opacity=0.7
                    ))

            # --- Réplicas de l'échantillon choisi ---
            for idx, spectrum in enumerate(self.data[sample_name]):
                fig.add_trace(go.Scatter(
                    x=self.bands,
                    y=spectrum,
                    mode="lines",
                    line=dict(color=color_sample, width=1.5),
                    name=f"{sample_name} - R{idx+1}",
                    opacity=0.9,
                    showlegend=(idx==0)
                ))

            # Ajouter les bandes spectrales si demandé
            if add_bands:
                fig = self.add_indicative_bands_plotly(fig)

            fig.update_layout(
                title=f"Comparaison : {sample_name} vs autres échantillons",
                xaxis_title="Bands (cm⁻¹)",
                yaxis_title="Absorbance",
                xaxis=dict(autorange="reversed"),
                legend=dict(itemsizing="constant", font=dict(size=12)),
                width=1200,
                height=600,
            )

            dict_fig[sample_name] = fig
        print(707, "end plot all samples vs others")
        return dict_fig     


### Pour save_res

class BasicFileUpload:
    def __init__(self, project: TriasProject):
        self.project: TriasProject = project
    
    def temp_save_datafiles(self, data, filename) -> str:
        if filename is None:
            temp_file = os.path.join(self._temp_path, "temp_file.json")
        else:
            temp_file = os.path.join(self._temp_path, filename)
        if os.path.splitext(filename)[1] == ".json":
            with open(temp_file, "w") as outfile:
                json.dump(data, outfile)
        elif os.path.splitext(filename)[1] == ".plotly":
            with open(temp_file, "w") as outfile:
                plotly.io.write_json(data, outfile)
        return temp_file

    def delete_temp_datafiles(self, temp_file):
        pathlib.Path.unlink(pathlib.Path(temp_file))
        return
    
    def upload_graph_data(self, graph_plotly, name, analysis):
        temp_file = self.temp_save_datafiles(graph_plotly, "temp.plotly")
        self.project.add_graph_data(analysis, temp_file, name)
        self.delete_temp_datafiles(temp_file)

# UTILS
def get_sample_name_and_rep_nb_from_filename_remscan(filename: str) -> tuple[str, str]:
    """
    get sample name from an .asp filename
    """
    sample_name = os.path.basename(filename)
    # removes .asp : "temp/YYYYMMDDHHMMSS-sample_name-replicate"
    sample_name = sample_name.replace(
        ".asp", ""
    )
    sample_name = sample_name.replace(
        ".json", ""
    )
    sample_name = sample_name[15:]  # "sample_name-replicate"
    # print(15, sample_name)
    regex_trailing_replicate_number = r"(.*)(\.|\-)(\d{1,3}$)"
    match_trailing_replicate_number = re.match(
        regex_trailing_replicate_number, sample_name
    )
    if match_trailing_replicate_number is not None:
        sample_name = match_trailing_replicate_number[1]  # split en deux parties: "sample_name"
        rep_nb = match_trailing_replicate_number[3]
        # print("re match_trailing_reeplicate_number", sample_name)
    else:
        rep_nb = "-1"  # no data value
        print("no trailing replicate number", sample_name)
    return sample_name, rep_nb

def get_sample_data_from_sample_name(
    sample_name: str, schema: str = ""
) -> dict[str, str | float]:
    """
    returns a dict with 3 keys: drilling, ph (profondeur haute), pb (profondeur basse)
    if function fails to find ph and pb they will be equal to float("nan")
    """
    if (
        re.match(r"(\d{14})(-|\.)", sample_name) is not None
    ):  ## checks if date is still there
        sample_name, rep_number = get_sample_name_and_rep_nb_from_filename_remscan(
            sample_name
        )  ## should remove date, replicate number, path, .asp
    if schema == "":
        # init rep_number in case it's unreadable
        rep_number = -1
        # Checks if there is something like drilling(number-number) number can be decimal, drilling can have a trailling whitespace
        regex_for_drilling_then_prof_in_parentheses = (
            r"(\w+\s?)(\(\d{1,2}((\.|\,)\d+)?)\-(\d{1,2}((\.|\,)\d+)?\))"
        )
        regex_for_drilling_then_prof_sep_by_dash_or_underscores = (
            r"(.*)(((\-|\_)(\d{1,2}((\.|\,)\d+)?))(\-|\_)(\d{1,2}((\.|\,)\d+)?))$"
        )
        regex_for_drilling_then_prof_sep_by_dots = (
            r"(.*)((\.)(\d{1,2}(\,\d+)?)(\.|\-)(\d{1,2}((\,)\d+)?))$"
        )
        match_prof_in_parentheses = re.match(
            regex_for_drilling_then_prof_in_parentheses, sample_name
        )
        match_prof_sep_by_dash = re.match(
            regex_for_drilling_then_prof_sep_by_dash_or_underscores, sample_name
        )
        match_prof_sep_by_dot = re.match(
            regex_for_drilling_then_prof_sep_by_dots, sample_name
        )
        regex_number_smthg_number = (
            r"([^\d])(\d{1,2}((\.|\,)\d+)?)\s?(\-|\_)\s?(\d{1,2}((\.|\,)\d+)?)"
        )
        match_number_smthg_number = re.search(
            regex_number_smthg_number, sample_name
        )

        if match_prof_in_parentheses is not None:  ## if found a match
            # print("Parentheses found")
            drilling: str = match_prof_in_parentheses[1].rstrip(
                " "
            )  ## find drilling, remove trailling whitespace
            ph: float = to_numeric(
                match_prof_in_parentheses[2].strip("(")
            )  ## find prof haute
            pb: float = to_numeric(
                match_prof_in_parentheses[5].rstrip(")")
            )  ## and prof basse

        elif match_prof_sep_by_dash is not None:
            # print("no parenthesis")
            drilling = match_prof_sep_by_dash[1].rstrip(
                " "
            )  ## find drilling, remove trailling whitespace
            ph = to_numeric(match_prof_sep_by_dash[5])  ## find prof haute
            pb = to_numeric(match_prof_sep_by_dash[9])  ## and prof basse
        elif match_prof_sep_by_dot is not None:
            print("dotss")
            drilling = match_prof_sep_by_dot[1].rstrip(
                " "
            )  ## find drilling, remove trailling whitespace
            ph = to_numeric(match_prof_sep_by_dot[4])  ## find prof haute
            pb = to_numeric(match_prof_sep_by_dot[7])  ## and prof basse
        elif match_number_smthg_number is not None:
            sample_name_without_number_smthg_number = re.split(regex_number_smthg_number, sample_name)[0]
            drilling = re.sub(r"\(|\)|\s", "", sample_name_without_number_smthg_number)
            ph = to_numeric(match_number_smthg_number[2])  ## find prof haute
            pb = to_numeric(match_number_smthg_number[6])  ## and prof basse
        else:
            # if something looks like number-number: those are suposed to be ph-pb and the rest is supposed to be drilling_name
            print("last ditch effort", sample_name)
            print(
                "cant decipher this, lets consider it as a drilling name",
                sample_name,
            )
            drilling = sample_name
            ph = float("nan")
            pb = float("nan")

    else:
        match_samplename = re.match(schema, sample_name)
        if match_samplename is not None:
            drilling = match_samplename[1]
            ph = float(match_samplename[3])
            pb = float(match_samplename[5])
    return {"drilling": drilling, "ph": ph, "pb": pb}


def to_numeric(string: str) -> float:
    """
    tries to transform a str to float, returns float('nan') on fail
    """
    try:
        num = float(string)
    except ValueError:
        try:
            num = float(string.replace(",", "."))
        except ValueError:
            return float("nan")
    return num


class TriasMethodSpectralVisualisationGreensi(TriasMethod):
    
    def format_data(self):
        t0 = time.perf_counter()
        spectra_array: list[Spectra] = [
            Spectra.from_sensor_data(sensor_data) for sensor_data in self.sensor_datas
        ]
        bands = spectra_array[0].bands
        all_spectra = np.array([s.spectra for s in spectra_array])
        sample_names = [s.sample_name for s in spectra_array]
        self.spectro = spectra_array[0].spectroscopy
        self.ouvrage = [str(x) for x in np.random.randint(0, 6, size=len(sample_names))] #TODO a remplacer par vecteur sondage
        self.ouvrage = []
        for spec in spectra_array:
            res = get_sample_data_from_sample_name(sample_name=spec.sample_name)
            self.ouvrage.append(res['drilling']) 

        self.data = {
            "spectro": self.spectro,
            "bands": bands,
            "spectra": all_spectra,
            "sample_names": sample_names
        }
        self.t_format_data = time.perf_counter() - t0

    async def main_execute(self) -> None:
        t0 = time.perf_counter()
        self.task.update("start main execute")

        spectral_viz = FigureSpectra(**self.data)

        self.task.update("62")
        self.result = {
            "Figures_sample": {"Spectra": spectral_viz.plot_spectra_plotly(add_bands=True),
                               "SpectraVsOthers": spectral_viz.plot_all_samples_vs_others(add_bands=True)},
            "Figures_ouvrage": spectral_viz.plot_spectra_by_class_plotly(classes=self.ouvrage, add_bands=True),
            "Figures_project": spectral_viz.plot_all_spectra_plotly(add_bands=True, plot_mean_only=True),
        }

        self.task.update("63")
        self.t_main_execute = time.perf_counter() - t0
        self.task.update(f"after plotting {self.t_main_execute}")

    def save_res(self):
        t0 = time.perf_counter()
        self.task.update("start save res")
        # stockage résultats echelle projet
        title = f"Visualisation des donnees spectrales"
        result_text = f"Visualisation des donnees spectrales"
        t0a = time.perf_counter()
        analysis: TriasAnalysis = self.save_analysis_project_scale(title, result_text)
        self.t_save_res_projet_analyze = time.perf_counter() - t0a
        ## stockage graphe échelle projet
        t0b = time.perf_counter()
        bfu = BasicFileUpload(self.project)
        bfu.upload_graph_data(self.result["Figures_project"] , title, analysis)
        self.t_save_res_projet_save = time.perf_counter() - t0b
        self.t_save_res_projet = time.perf_counter() - t0
        self.task.update(f"after plotting {self.t_save_res_projet}")

        fig_json_str = self.result["Figures_project"].to_json()  # sérialise la figure en JSON
        size_bytes = len(fig_json_str.encode('utf-8'))           # taille en octets
        size_kb = size_bytes / 1024
        size_mb = size_kb / 1024
        print(f"Taille figure projet : {size_bytes} B / {size_kb:.2f} KB / {size_mb:.2f} MB")

        # stockage résultats echelle ouvrage
        self.task.update("start stockage ouvrage")
        t0 = time.perf_counter()
        for i, drill in enumerate(self.project.get_drillings()):
            drill_name = drill.get_name()

            if drill_name not in self.result["Figures_ouvrage"]:
                print(f"Aucun résultat pour l’ouvrage '{drill_name}' — skipping.")
                continue   # on passe au drilling suivant

            t0a = time.perf_counter()
            print(1, drill, drill_name)
            if drill.has_drilling_viz():
                print(11)
                analysis: TriasDrillingViz = drill.get_drilling_viz()
            else:
                print(12)
                analysis: TriasDrillingViz = drill.create_drilling_viz(delete_existing=False)
            print(2)

            self.t_save_res_drilling_analyze = time.perf_counter() - t0a
           
            ## stockage graphe échelle ouvrage
            t0b = time.perf_counter()
            bfu = BasicFileUpload(self.project) 
            bfu.upload_graph_data(self.result["Figures_ouvrage"][drill.get_name()], f"Visualisation des données spectrales de {drill.get_name()}", analysis)
            self.t_save_res_drilling_save = time.perf_counter() - t0b
        self.t_save_res_drilling = time.perf_counter() - t0
        self.task.update(f"after stockage ouvrage {self.t_save_res_drilling}")

        fig_json_str = self.result["Figures_ouvrage"][drill.get_name()].to_json()  # sérialise la figure en JSON
        size_bytes = len(fig_json_str.encode('utf-8'))           # taille en octets
        size_kb = size_bytes / 1024
        size_mb = size_kb / 1024
        print(f"Taille ouvrage projet : {size_bytes} B / {size_kb:.2f} KB / {size_mb:.2f} MB")

        # stockage résultats echelle échantillon
        t0 = time.perf_counter()
        for i, samp in enumerate(self.project.get_all_samples()):
            samp_name = samp.get_name()

            if samp_name not in self.result["Figures_sample"]["Spectra"]:
                print(f"Aucun résultat pour l'échantillon '{samp_name}' — skipping.")
                continue   # on passe a l'échantillon suivant
            if samp.has_spectral_viz():
                analysis: TriasSpectralViz = samp.get_spectral_viz()
            else:
                analysis: TriasSpectralViz = samp.create_spectral_viz(delete_existing=False)
            ## stockage graphe échelle ouvrage
            bfu = BasicFileUpload(self.project)
            bfu.upload_graph_data(self.result["Figures_sample"]["Spectra"][samp_name], f"Visualisation des données spectrales de {samp_name}", analysis)
            bfu.upload_graph_data(self.result["Figures_sample"]["SpectraVsOthers"][samp_name], f"Visualisation des données spectrales de {samp_name} en fonction des autres échantillons", analysis)
        self.t_save_res_sample = time.perf_counter() - t0

        fig_json_str = self.result["Figures_sample"]["Spectra"][samp_name].to_json()  # sérialise la figure en JSON
        size_bytes = len(fig_json_str.encode('utf-8'))           # taille en octets
        size_kb = size_bytes / 1024
        size_mb = size_kb / 1024
        print(f"Taille sample projet : {size_bytes} B / {size_kb:.2f} KB / {size_mb:.2f} MB")

        print(f"[TIME] format_data : {self.t_format_data:.3f} s")
        print(f"[TIME] main_execute : {self.t_main_execute:.3f} s")
        print(f"[TIME] save_res_projet : {self.t_save_res_projet:.3f} s")
        print(f"[TIME] save_res_projet_analyze : {self.t_save_res_projet_analyze:.3f} s")
        print(f"[TIME] save_res_projet_save : {self.t_save_res_projet_save:.3f} s")
        print(f"[TIME] save_res_drilling : {self.t_save_res_drilling:.3f} s")
        print(f"[TIME] save_res_drilling_analyze : {self.t_save_res_drilling_analyze:.3f} s")
        print(f"[TIME] save_res_drilling_save : {self.t_save_res_drilling_save:.3f} s")
        print(f"[TIME] save_res_sample : {self.t_save_res_sample:.3f} s")


CLIENT_TEST = CeFormsClient(
    base_url="https://trias.codeffekt.ovh/beta/apis/trias/",
    token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJjZS1mb3Jtcy1hcGkiLCJzdWIiOiJqLmVsaWFzQGVudmlzb2wuZnIiLCJ1aWQiOiJhZTcxNTdjMC1jMWFmLTRkMmUtYWI4MC1kMWVlZmM4ZTNlOTAiLCJleHAiOjg1Nzk2NjU0MjcsImlhdCI6MTczNjM1MzQyN30.qGAHuY7jczx_D58GYTcLXnWoPrjsw9cWLE760u-uK0w",
)

# Non utilisé ici
def create_app():
    TriasMethodFactory.register("Spectral visualisation", TriasMethodSpectralVisualisationGreensi)
    return TriasProcessing.create_app(CLIENT_TEST)

if __name__ == "__main__":
    print("hello")
    id_method_spectral_viz_prj = "0ca251e7-200f-4351-9b95-df1b19ec808d"
    
    client = CLIENT_TEST
    
    TriasMethodFactory.register("Spectral visualisation", TriasMethodSpectralVisualisationGreensi)
    form = TriasProcessing.do_processing_sync(client, id_method_spectral_viz_prj)
