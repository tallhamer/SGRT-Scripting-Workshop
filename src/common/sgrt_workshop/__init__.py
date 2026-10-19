"""sgrt_workshop — what every product's workshop in this repository shares.

The list of workshops (:mod:`~sgrt_workshop.products`) and the ``<product>-workshop`` launcher
(:mod:`~sgrt_workshop.launcher`). Product-specific code lives in that product's own packages under
``src/<product>/``.

Not a medical device. Teaching use only. Not affiliated with or endorsed by Vision RT.
"""

from sgrt_workshop.products import PRODUCTS, Product

__all__ = ["PRODUCTS", "Product"]
