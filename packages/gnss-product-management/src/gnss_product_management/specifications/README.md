# `specifications/`: The Definitive Blueprints for GNSS Products

Alright, pay attention, because this `specifications/` directory is the very foundation upon which our entire GNSS product handling system is built. This is where we meticulously define *everything* about the products we care about – what they are, how they're formatted, where they come from, and what metadata they contain. Think of it as the ultimate set of blueprints and dictionaries that allow our system to understand and interact with the complex world of GNSS data.

This module houses several critical sub-modules, each dedicated to defining a particular aspect of our data landscape:

### `parameters/`: The Metadata Glossary
*   This module (and its corresponding `meta_spec.yaml` in `configs/meta/`) defines all the individual metadata fields (like `YYYY`, `AAA`, `GPSWEEK`) that appear in filenames and descriptions. It specifies their patterns, descriptions, and how they're derived. It's the dictionary for all those arcane abbreviations.

### `format/`: The File Format Rulebook
*   This module (and `format_spec.yaml` in `configs/products/`) defines the concrete structures and naming conventions for different file formats (e.g., RINEX versions 2, 3, 4; our generic `PRODUCT` format; VMF). It provides filename templates and lists the parameters that populate them. It tells us *how* a file is physically laid out and named.

### `products/`: The Product Catalogue
*   This module (and `product_spec.yaml` in `configs/products/`) defines the abstract types of GNSS products we process (e.g., `ORBIT`, `CLOCK`, `IONEX`). For each product type, it specifies its general characteristics, what formats it can take, and any high-level constraints. It tells us *what* a particular product conceptually is.

### `remote/`: The Remote Resource Directory
*   This module defines how remote data sources (like IGS, CDDIS, GFZ) are specified. It covers details like server hostnames, protocols (FTP, FTPS, SFTP, HTTP), authentication requirements, and the specific product offerings from each analysis center. It tells us *where* to find products remotely.

### `local/`: The Local Archive Layout
*   This module defines how downloaded GNSS products are organized and stored on our local disk. It specifies directory structures, temporal categories (daily, static), and logical collections of products, linking them to physical paths. It tells us *where* to store products locally.

### `dependencies/`: The Product Shopping Lists
*   This module defines *dependency specifications*, which are bundles of required products for specific processing engines or tasks. It also includes preference rules for selecting products from different analysis centers or solution types. It tells us *what combination of products* is needed for a particular job.

### `queries/`: The Search Dimensions
*   This module (and `query_config.yaml` in `configs/query/`) defines the "search axes" – the user-facing parameters (like `date`, `center`, `solution`) that can be used to query for GNSS products. It maps these axes to underlying metadata fields and specifies how they apply to different product types. It tells us *how to ask* for specific products.

### `catalog.py`: The Compiler
*   While not a subdirectory, `catalog.py` is a crucial file within this module. It houses the logic for building the various "catalogs" (like `ProductCatalog`, `FormatCatalog`) by taking the raw specifications defined in the YAML files and compiling them into highly efficient, interconnected Python objects. This compilation step transforms static definitions into a dynamic, usable knowledge base.

In essence, the `specifications/` module is the beating heart of our ETL system's intelligence. It translates the messy, real-world complexity of GNSS data into an ordered, machine-readable format, enabling everything from dynamic query generation to reliable file fetching and local storage. Don't go mucking about with these definitions lightly; they are the very ground rules of our operation!
