---
jupyter:
  jupytext:
    formats: ipynb,md
    text_representation:
      extension: .md
      format_name: markdown
      format_version: '1.3'
      jupytext_version: 1.11.2
  kernelspec:
    display_name: Python 3
    language: python
    name: python3
---

## Handling datasets with multiple modalities

```python
%load_ext autotime
%config InlineBackend.figure_format = 'retina'

import scarf
scarf.__version__
```

---
### 1) Fetch and convert data

For this tutorial we will use CITE-Seq data from 10x genomics. This dataset contains two modalities: gene expression and surface protein abundance. Throughout this tutorial we will refer to gene expression modality as `RNA` and surface protein as `ADT`. We start by downloading the data and converting it into Zarr format:

```python
scarf.fetch_dataset('tenx_8K_pbmc_citeseq', save_path='scarf_datasets')
```

```python
reader = scarf.CrH5Reader('scarf_datasets/tenx_8K_pbmc_citeseq/data.h5', 'rna')
```

We can also quickly check the different kinds of assays present in the file and the number of features from each of them.

```python
reader.assayFeats
```

The **nFeatures** column shows the number of features present in each assay. `CrH5Reader` will automatically pull this information from H5 file and rename the 'Gene Expression' assay to **RNA**. Here it also found another assay: 'Antibody Capture' and named it to **assay2**. We will rename this to **ADT**.

```python
reader.rename_assays({'assay2': 'ADT'})
reader.assayFeats
```

Now the data is converted into Zarr format. Like single assay datasets, all the data is saved under one Zarr file.

```python
writer = scarf.CrToZarr(reader, zarr_fn='scarf_datasets/tenx_8K_pbmc_citeseq/data.zarr',
                        chunk_size=(2000, 1000))
writer.dump(batch_size=1000)
```

---
### 2) Create a multimodal DataStore

The next step is to create a Scarf `DataStore` object. This object will be the primary way to interact with the data and all its constituent assays. The first time a Zarr file is loaded, we need to set the default assay. Here we set the 'RNA' assay as the default assay. When a Zarr file is loaded, Scarf checks if some per-cell statistics have been calculated. If not, then **nFeatures** (number of features per cell) and **nCounts** (total sum of feature counts per cell) are calculated. Scarf will also attempt to calculate the percent of mitochondrial and ribosomal content per cell.

```python
ds = scarf.DataStore('scarf_datasets/tenx_8K_pbmc_citeseq/data.zarr',
                     default_assay='RNA',
                     nthreads=4)
```

We can print out the DataStore object to get an overview of all the assays stored.

```python
ds
```

Feature attribute tables for each of the assays can be accessed like this:

```python
ds.RNA.feats.head()
```

```python
ds.ADT.feats.head()
```

Cell filtering is performed based on the default assay. Here we use the `auto_filter_cells` method of the `DataStore` to filter low quality cells.

```python
ds.auto_filter_cells()
```

---
### 3) Process gene expression modality

Now we process the RNA assay to perform feature selection, create KNN graph, run UMAP reduction and clustering. These steps are same as shown in the basic workflow for scRNA-Seq data.

```python
ds.mark_hvgs(min_cells=20, top_n=500, min_mean=-3, max_mean=2, max_var=6)
ds.make_graph(feat_key='hvgs', k=11, dims=15, n_centroids=100)
ds.run_umap(fit_n_epochs=250, spread=5, min_dist=1, parallel=True)
ds.run_leiden_clustering(resolution=1)
```

```python
ds.plot_layout(layout_key='RNA_UMAP', color_by='RNA_leiden_cluster')
```

---
### 4) Process protein surface abundance modality


We will now perform similar steps as RNA for the ADT data. Since ADT panels are often custom designed, we will not perform any feature selection step. This particular data contains some control antibodies which we should filter out before downstream analysis. 

```python
ds.ADT.feats.head(n=ds.ADT.feats.N)
```

We can manually filter out the control antibodies by updating **I** to be False for those features. To do so we first extract the names of all the ADT features like below:

```python
adt_names = ds.ADT.feats.to_pandas_dataframe(['names'])['names']
adt_names
```

The ADT features with 'control' in name are designated as control antibodies. You can have your own selection criteria here. The aim here is to create a boolean array that has `True` value for features to be removed.

```python
is_control = adt_names.str.contains('control').values
is_control
```

Now we update `I` to remove the control features. `update_key` method takes a boolean array and disables the features that have `False` value. So we invert the above created array (using `~`) before providing it to `update_key`. The second parameter for `update_key` denotes which feature table boolean column to modify, `I` in this case.

```python
ds.ADT.feats.update_key(~is_control, 'I')
ds.ADT.feats.head(n=ds.ADT.feats.N)
```

Assays named ADT are automatically created as objects of the `ADTassay` class, which uses CLR (centred log ratio) normalization as the default normalization method.

```python
print (ds.ADT)
print (ds.ADT.normMethod.__name__)
```

Now we are ready to create a KNN graph of cells using only ADT data. Here we will use all the features (except those that were filtered out) and that is why we use `I` as value for `feat_key`. It is important to note the value for `from_assay` parameter which has now been set to `ADT`. If no value is provided for `from_assay` then it is automatically set to the default assay. 

```python
ds.make_graph(from_assay='ADT', feat_key='I', k=11, dims=11, n_centroids=100)
```

UMAP and clustering can be run on ADT assay by simply setting `from_assay` parameter value to 'ADT':

```python
ds.run_umap(from_assay='ADT', fit_n_epochs=250, spread=5, min_dist=1, parallel=True)
ds.run_leiden_clustering(from_assay='ADT', resolution=1)
```

If we now check the cell attribute table, we will find the UMAP coordinates and clusters calculated using `ADT` assay:

```python
ds.cells.head()
```

Visualizing the UMAP and clustering calcualted using `ADT` only:

```python
ds.plot_layout(layout_key='ADT_UMAP', color_by='ADT_leiden_cluster')
```

---
### 5) Cross modality comparison

It is generally of interest to see how different modalities corroborate each other.

```python
# UMAP on RNA and coloured with clusters calculated on ADT
ds.plot_layout(layout_key='RNA_UMAP', color_by='ADT_leiden_cluster')
```

```python
# UMAP on ADT and coloured with clusters calculated on RNA
ds.plot_layout(layout_key='ADT_UMAP', color_by='RNA_leiden_cluster')
```

We can quantify the overlap of cells between RNA and ADT clusters. The following table has ADT clusters on columns and RNA clusters on rows. This table shows a cross tabulation of cells across the clustering from the two modalities.

```python
import pandas as pd

df = pd.crosstab(ds.cells.fetch('RNA_leiden_cluster'),
                 ds.cells.fetch('ADT_leiden_cluster'))
df
```

There are possibly many interesting strategies to analyze this further. One simple way to summarize the above table can be quantify the transcriptomics 'purity' of ADT clusters:

```python
(100 * df.max()/df.sum()).sort_values(ascending=False)
```

Individual ADT expression can be visualized in both UMAPs easily.

```python
ds.plot_layout(from_assay='ADT', layout_key='ADT_UMAP', color_by='CD16_TotalSeqB')
ds.plot_layout(from_assay='ADT', layout_key='RNA_UMAP', color_by='CD16_TotalSeqB')
```

We can also query gene expression and visualize it on both RNA and ADT UMAPs. Here we query gene FCGR3A which codes for CD16:

```python
ds.plot_layout(from_assay='RNA', layout_key='RNA_UMAP', color_by='FCGR3A')
ds.plot_layout(from_assay='RNA', layout_key='ADT_UMAP', color_by='FCGR3A')
```

---
That is all for this vignette.
