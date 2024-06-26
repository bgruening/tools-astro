#!/usr/bin/env python
# coding: utf-8

# flake8: noqa

import json
import os
import shutil

import matplotlib.pyplot as plt
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from numpy import log10, sqrt
from oda_api.data_products import ODAAstropyTable, PictureProduct
from oda_api.json import CustomJSONEncoder

if os.path.exists("hess_dl3_dr1.tar.gz") == False:
    get_ipython().system(   # noqa: F821
        "wget https://zenodo.org/record/1421099/files/hess_dl3_dr1.tar.gz"
    )
    get_ipython().system("tar -zxvf hess_dl3_dr1.tar.gz")   # noqa: F821
from oda_api.api import ProgressReporter

pr = ProgressReporter()
pr.report_progress(stage="Progress", progress=0.0)

# src_name='Crab' #http://odahub.io/ontology#AstrophysicalObject
# RA = 83.628700  # http://odahub.io/ontology#PointOfInterestRA
# DEC = 22.014700 # http://odahub.io/ontology#PointOfInterestDEC
src_name = "PKS 2155-304"  # http://odahub.io/ontology#AstrophysicalObject
RA = 329.716938  # http://odahub.io/ontology#PointOfInterestRA
DEC = -30.225588  # http://odahub.io/ontology#PointOfInterestDEC

T1 = "2000-10-09T13:16:00.0"  # http://odahub.io/ontology#StartTime
T2 = "2022-10-10T13:16:00.0"  # http://odahub.io/ontology#EndTime
Radius = 2.5  # http://odahub.io/ontology#AngleDegrees
R_s = 0.2  # http://odahub.io/ontology#AngleDegrees

Emin = 0.1  # http://odahub.io/ontology#Energy_TeV
Emax = 100.0  # http://odahub.io/ontology#Energy_TeV
NEbins = 30  # http://odahub.io/ontology#Integer

Efit_min = 0.2  # http://odahub.io/ontology#Energy_TeV
Efit_max = 10.0  # http://odahub.io/ontology#Energy_TeV

_galaxy_wd = os.getcwd()

with open("inputs.json", "r") as fd:
    inp_dic = json.load(fd)
if "_data_product" in inp_dic.keys():
    inp_pdic = inp_dic["_data_product"]
else:
    inp_pdic = inp_dic

for vn, vv in inp_pdic.items():
    if vn != "_selector":
        globals()[vn] = type(globals()[vn])(vv)

E0 = 1.0

def model_dNdE(E, N, Gam):
    return N * (E / E0) ** (Gam)

def model_rate(E1, E2, N, Gam):
    dEE = E2 - E1
    EE = sqrt(E1 * E2)
    return model_dNdE(EE, N, Gam) * dEE

Ebins = np.logspace(log10(Emin), log10(Emax), NEbins + 1)
Emins = Ebins[:-1]
Emaxs = Ebins[1:]
Emeans = sqrt(Emins * Emaxs)
lgEmeans = log10(Emeans)
dE = Ebins[1:] - Ebins[:-1]

T1 = Time(T1, format="isot", scale="utc").mjd
T2 = Time(T2, format="isot", scale="utc").mjd
message = ""
RA_pnts = []
DEC_pnts = []
DL3_files = []
OBSIDs = []
Tstart = []
Tstop = []
flist = os.listdir("data")
for f in flist:
    if f[-7:] == "fits.gz":
        DL3_files.append(f)
        OBSIDs.append(int(f[20:26]))
        hdul = fits.open("data/" + f)
        RA_pnts.append(float(hdul[1].header["RA_PNT"]))
        DEC_pnts.append(float(hdul[1].header["DEC_PNT"]))
        Tstart.append(
            Time(
                hdul[1].header["DATE-OBS"] + "T" + hdul[1].header["TIME-OBS"],
                format="isot",
                scale="utc",
            ).mjd
        )
        Tstop.append(
            Time(
                hdul[1].header["DATE-END"] + "T" + hdul[1].header["TIME-END"],
                format="isot",
                scale="utc",
            ).mjd
        )
        hdul.close()

Coords_s = SkyCoord(RA, DEC, unit="degree")
COORDS_pnts = SkyCoord(RA_pnts, DEC_pnts, unit="degree")
seps = COORDS_pnts.separation(Coords_s).deg

mask = np.where((seps < Radius) & (Tstart > T1) & (Tstop < T2))[0]
OBSlist = []
for i in mask:
    OBSlist.append(DL3_files[i])
if len(OBSlist) == 0:
    message = "No data found"
    raise RuntimeError("No data found")
offaxis = seps[mask]
Tstart = np.array(Tstart)[mask]
print("Found", len(Tstart), "pointings")

ind = 0
pointing = OBSlist[ind]
hdul = fits.open("data/" + pointing)
RMF = hdul["EDISP"].data
ENERG_LO = RMF["ENERG_LO"][0]
ENERG_HI = RMF["ENERG_HI"][0]
MIGRA_LO = RMF["MIGRA_LO"][0]  # MIGRA_bins=np.linspace(0.2,5,161)
MIGRA_HI = RMF["MIGRA_HI"][0]
MIGRA = (MIGRA_LO + MIGRA_HI) / 2.0
ENERG = sqrt(ENERG_LO * ENERG_HI)
dENERG = ENERG_HI - ENERG_LO

cts_s = []
cts_b = []
Eff_area = []
Eff_area_interp = []
Texp = []
RMFs = []
for ind in range(len(OBSlist)):
    pointing = OBSlist[ind]
    hdul = fits.open("data/" + pointing)

    RA_pnt = hdul[1].header["RA_PNT"]
    DEC_pnt = hdul[1].header["DEC_PNT"]
    Texp.append(hdul[1].header["LIVETIME"])
    dRA = RA - RA_pnt
    dDEC = DEC - DEC_pnt
    RA_b = RA_pnt - dRA
    DEC_b = DEC_pnt - dDEC
    Coords_b = SkyCoord(RA_b, DEC_b, unit="degree")
    Coords_pnt = SkyCoord(RA_pnt, DEC_pnt, unit="degree")
    dist = Coords_pnt.separation(Coords_s).deg

    RMF = hdul["EDISP"].data
    mask = RMF["THETA_LO"] < dist
    ind_th = len(RMF["THETA_LO"][mask]) - 1
    RMF_th = RMF["MATRIX"][0][ind_th]
    RMF_interp = np.zeros((len(Emeans), len(ENERG)))
    for k in range(len(ENERG)):
        dp_dErec = RMF_th[:, k] / ENERG[k]
        Erec = MIGRA * ENERG[k]
        dp_dErec_interp = (
            np.interp(Emeans, Erec, dp_dErec)
            * (Emeans > min(Erec))
            * (Emeans < max(Erec))
        )
        RMF_interp[:, k] = dp_dErec_interp
    RMFs.append(RMF_interp)

    AEFF = hdul["AEFF"].data
    Eff_area.append(AEFF["EFFAREA"][0][ind_th])
    Eff_area_interp.append(np.interp(Emeans, ENERG, Eff_area[-1]))

    ev = hdul["EVENTS"].data
    ev_ra = ev["RA"]
    ev_dec = ev["DEC"]
    ev_en = ev["ENERGY"]
    ev_time = ev["TIME"]
    ev_coords = SkyCoord(ev_ra, ev_dec, unit="degree")
    sep_s = ev_coords.separation(Coords_s).deg
    sep_b = ev_coords.separation(Coords_b).deg

    mask = sep_s < R_s
    cts_s.append(np.histogram(ev_en[mask], bins=Ebins)[0])
    mask = sep_b < R_s
    cts_b.append(np.histogram(ev_en[mask], bins=Ebins)[0])
    hdul.close()

cts_s = np.array(cts_s)
cts_b = np.array(cts_b)
Eff_area = np.array(Eff_area)
Eff_area_interp = np.array(Eff_area_interp)
Texp = np.array(Texp)

cts_s_tot = sum(cts_s)
cts_b_tot = sum(cts_b)
src_tot = cts_s_tot - cts_b_tot
src_tot_err = sqrt(cts_s_tot + cts_b_tot)
Expos_tot_interp = sum(Eff_area_interp * np.outer(Texp, np.ones(NEbins))) * 1e4
flux_tot = src_tot / (Expos_tot_interp + 1) / (Emaxs - Emins) * Emaxs * Emins
flux_tot_err = (
    src_tot_err / (Expos_tot_interp + 1) / (Emaxs - Emins) * Emaxs * Emins
)
print(
    "Total source counts:",
    sum(cts_s_tot),
    "; background counts",
    sum(cts_b_tot),
)

def model_cts_Erec(N, Gam):
    model_ENERG = model_rate(ENERG_LO, ENERG_HI, N, Gam)
    res = np.zeros(NEbins)
    for ind in range(len(OBSlist)):
        model_counts_ENERG = model_ENERG * Eff_area[ind] * 1e4 * Texp[ind]
        for k in range(len(ENERG)):
            res += model_counts_ENERG[k] * RMFs[ind][:, k] * dE
    return res

def chi2(p):
    N, slope = p
    counts = model_cts_Erec(N, slope)
    m = Emeans > Efit_min
    m &= Emeans < Efit_max
    m &= src_tot_err > 0.0
    chi2 = (((counts[m] - src_tot[m]) / src_tot_err[m]) ** 2).sum()
    dof = sum(m)
    # print(N,slope,chi2)
    return chi2, dof

plt.errorbar(
    Emeans,
    src_tot,
    src_tot_err,
    xerr=[Emeans - Emins, Emaxs - Emeans],
    linestyle="none",
)

plt.axvline(Efit_min, color="black")
plt.axvline(Efit_max, color="black")
plt.xscale("log")
plt.yscale("log")
N = 4e-11
Gam = -2.7
plt.plot(Emeans, model_cts_Erec(N, Gam))
chi2([N, Gam])[0]

# 1) find 90% confidence contour scanning over a wide parameter space
Norm_max = 1e-10
Norm_min = 1e-12
Norm_bins = 100
Gam_min = -1.0
Gam_max = -5.0
Gam_bins = 100
Ns = np.linspace(Norm_min, Norm_max, Norm_bins)
Gams = np.linspace(Gam_min, Gam_max, Gam_bins)
chi2_map = np.zeros((Norm_bins, Gam_bins))
Norm_best = Norm_min
Gam_best = Gam_min
chi2_best = 1e10
for i, N in enumerate(Ns):
    pr.report_progress(stage="Progress", progress=5 + 45 * i / Norm_bins)
    for j, Gam in enumerate(Gams):
        chi2_map[i, j] = chi2([N, Gam])[0]
        if chi2_map[i, j] < chi2_best:
            Norm_best = N
            Gam_best = Gam
            chi2_best = chi2_map[i, j]
print(Norm_best, Gam_best)
# plt.imshow(chi2_map,vmax=np.amin(chi2_map)+4,origin='lower',extent=[Gams[0],Gams[-1],Ns[0],Ns[-1]],aspect=(Gams[-1]-Gams[0])/(Ns[-1]-Ns[0]))

# 68% contour from https://ui.adsabs.harvard.edu/abs/1976ApJ...208..177L/abstract for two-parameter fit
# 90% contour from https://ui.adsabs.harvard.edu/abs/1976ApJ...208..177L/abstract for two-parameter fit

cnt = plt.contour(
    Gams, Ns, chi2_map, levels=[np.amin(chi2_map) + 4.61], colors="red"
)
plt.scatter([Gam_best], [Norm_best], marker="x", color="red")
# plt.colorbar()
print(np.amin(chi2_map))

cont = cnt.get_paths()[0].vertices
gammas = cont[:, 0]
norms = cont[:, 1]

# 2) refine with 68% contour calculation within the initial 90% countour
Norm_max = max(1.1 * norms)
Norm_min = min(0.9 * norms)
Norm_bins = 50
Gam_min = min(gammas - 0.2)
Gam_max = max(gammas + 0.2)
Gam_bins = 50
Ns = np.linspace(Norm_min, Norm_max, Norm_bins)
Gams = np.linspace(Gam_min, Gam_max, Gam_bins)
chi2_map = np.zeros((Norm_bins, Gam_bins))
Norm_best = Norm_min
Gam_best = Gam_min
chi2_best = 1e10
for i, N in enumerate(Ns):
    pr.report_progress(stage="Progress", progress=50 + 50 * i / Norm_bins)
    for j, Gam in enumerate(Gams):
        chi2_map[i, j] = chi2([N, Gam])[0]
        if chi2_map[i, j] < chi2_best:
            Norm_best = N
            Gam_best = Gam
            chi2_best = chi2_map[i, j]
print(Norm_best, Gam_best)
# plt.imshow(chi2_map,vmax=np.amin(chi2_map)+4,origin='lower',extent=[Gams[0],Gams[-1],Ns[0],Ns[-1]],aspect=(Gams[-1]-Gams[0])/(Ns[-1]-Ns[0]))

# 68% contour from https://ui.adsabs.harvard.edu/abs/1976ApJ...208..177L/abstract for two-parameter fit
cnt = plt.contour(
    Gams, Ns, chi2_map, levels=[np.amin(chi2_map) + 2.3], colors="black"
)
cont = cnt.get_paths()[0].vertices
gammas = cont[:, 0]
norms = cont[:, 1]

plt.scatter([Gam_best], [Norm_best], marker="x", color="black")
# plt.colorbar()
print(chi2([Norm_best, Gam_best]))
plt.xlabel("Slope")
plt.ylabel(r"Norm, 1/(TeV cm$^2$ s)")
plt.savefig("Contour.png", format="png", bbox_inches="tight")

plt.figure(figsize=(8, 6))
x = np.logspace(log10(Efit_min), log10(Efit_max), 10)
ymax = np.zeros(10)
ymin = np.ones(10)
for i in range(len(gammas)):
    y = model_dNdE(x, norms[i], gammas[i]) * x**2
    ymax = np.maximum(y, ymax)
    ymin = np.minimum(y, ymin)
    # plt.plot(x,y)
plt.fill_between(x, ymin, ymax, alpha=0.2)
plt.plot(x, model_dNdE(x, Norm_best, Gam_best) * x**2)

plt.errorbar(
    Emeans,
    flux_tot,
    flux_tot_err,
    xerr=[Emeans - Emins, Emaxs - Emeans],
    linestyle="none",
    color="black",
    linewidth=2,
)

# plt.axvspan(0, Efit_min, alpha=0.2, color='black')
# plt.axvspan(Efit_max, 1000, alpha=0.2, color='black')

plt.xscale("log")
plt.yscale("log")
plt.xlim(0.1, 100)
plt.xlabel("$E$, TeV")
plt.ylabel("$E^2 dN/dE$, TeV/(cm$^2$ s)")
plt.savefig("Spectrum.png", format="png", bbox_inches="tight")

print("Here")
new_hdul = fits.HDUList()
form = str(len(ENERG)) + "E"

for i in range(len(OBSlist)):
    col1 = fits.Column(name="COUNTS", format="E", array=cts_s[i])
    col2 = fits.Column(name="BACKGROUND", format="E", array=cts_b[i])
    hdu = fits.BinTableHDU.from_columns([col1, col2], name="COUNTS")
    new_hdul.append(hdu)
    col = fits.Column(format=form, array=RMFs[i], name="RMF")
    hdu = fits.BinTableHDU.from_columns([col], name="RMF")
    new_hdul.append(hdu)
    col = fits.Column(format="E", array=Eff_area[i], name="ARF")
    hdu = fits.BinTableHDU.from_columns([col], name="ARF")
    new_hdul.append(hdu)

col1 = fits.Column(name="E_MIN", format="E", unit="TeV", array=Emins)
col2 = fits.Column(name="E_MAX", format="E", unit="TeV", array=Emaxs)
cols = fits.ColDefs([col1, col2])
hdu = fits.BinTableHDU.from_columns(cols, name="Erec_BOUNDS")
new_hdul.append(hdu)
col1 = fits.Column(name="ENERG_LO", format="E", unit="TeV", array=ENERG_LO)
col2 = fits.Column(name="ENERG_HI", format="E", unit="TeV", array=ENERG_HI)
cols = fits.ColDefs([col1, col2])
hdu = fits.BinTableHDU.from_columns(cols, name="Etrue_BOUNDS")
new_hdul.append(hdu)
# new_hdul.writeto('Spectra.fits',overwrite=True)

print("and here")
bin_image = PictureProduct.from_file("Spectrum.png")
bin_image1 = PictureProduct.from_file("Contour.png")
from astropy.table import Table

data = [Emeans, Emins, Emaxs, flux_tot, flux_tot_err]
names = (
    "Emean[TeV]",
    "Emin[TeV]",
    "Emax[TeV]",
    "Flux[TeV/cm2s]",
    "Flux_error[TeV/cm2s]",
)
spec = ODAAstropyTable(Table(data, names=names))

data = [
    np.concatenate(([Gam_best], gammas)),
    np.concatenate(([Norm_best], norms)),
]
names = ["Gamma", "Norm_1TeV[1/(TeV cm2 s)]"]
error_ellipse = ODAAstropyTable(Table(data, names=names))

png = bin_image  # http://odahub.io/ontology#ODAPictureProduct
table_confidence_contour = (
    error_ellipse  # http://odahub.io/ontology#ODAAstropyTable
)
table_spectrum = spec  # http://odahub.io/ontology#ODAAstropyTable

# output gathering
_galaxy_meta_data = {}
_oda_outs = []
_oda_outs.append(("out_Spectrum_png", "png_galaxy.output", png))
_oda_outs.append(
    (
        "out_Spectrum_table_confidence_contour",
        "table_confidence_contour_galaxy.output",
        table_confidence_contour,
    )
)
_oda_outs.append(
    (
        "out_Spectrum_table_spectrum",
        "table_spectrum_galaxy.output",
        table_spectrum,
    )
)

for _outn, _outfn, _outv in _oda_outs:
    _galaxy_outfile_name = os.path.join(_galaxy_wd, _outfn)
    if isinstance(_outv, str) and os.path.isfile(_outv):
        shutil.move(_outv, _galaxy_outfile_name)
        _galaxy_meta_data[_outn] = {"ext": "_sniff_"}
    elif getattr(_outv, "write_fits_file", None):
        _outv.write_fits_file(_galaxy_outfile_name)
        _galaxy_meta_data[_outn] = {"ext": "fits"}
    elif getattr(_outv, "write_file", None):
        _outv.write_file(_galaxy_outfile_name)
        _galaxy_meta_data[_outn] = {"ext": "_sniff_"}
    else:
        with open(_galaxy_outfile_name, "w") as fd:
            json.dump(_outv, fd, cls=CustomJSONEncoder)
        _galaxy_meta_data[_outn] = {"ext": "json"}

with open(os.path.join(_galaxy_wd, "galaxy.json"), "w") as fd:
    json.dump(_galaxy_meta_data, fd)
print("*** Job finished successfully ***")
