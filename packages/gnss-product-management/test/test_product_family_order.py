"""Regression checks for timeliness-first families and independent mirrors."""

import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from gnss_product_management.client.product_query import ProductQuery
from gnss_product_management.factories.models import FoundResource
from gnss_product_management.factories.pipelines.resolve import ResolvePipeline
from gnss_product_management.specifications.dependencies.dependencies import (
    Dependency,
    DependencyBundle,
    DependencySpec,
)

SPEC = Path(__file__).parents[2] / "pride-ppp/src/pride_ppp/configs/dependencies/pride_pppar.yaml"


def candidate(product, ac, quality, host):
    return FoundResource(
        product=product,
        source="remote",
        uri=f"https://{host}/{ac}/{quality}/{product}",
        parameters={"AAA": ac, "TTT": quality, "PPP": "MGX"},
    )


def test_timeliness_precedes_ac_and_mirrors_are_exhausted():
    spec = DependencySpec.from_yaml(SPEC)
    pipeline = ResolvePipeline.__new__(ResolvePipeline)
    products = ["ORBIT", "CLOCK"]
    candidates = {
        product: [
            candidate(product, ac, quality, host)
            for ac, quality, host in [
                ("WUM", "RTS", "wuhan"),
                ("COD", "FIN", "primary"),
                ("COD", "FIN", "mirror"),
            ]
        ]
        for product in products
    }
    pipeline._search_candidates = MagicMock(side_effect=lambda dep, **kw: candidates[dep.spec])
    pipeline._downloader = MagicMock()
    pipeline._downloader.run.side_effect = lambda found, *a, **kw: (
        None
        if found.product == "CLOCK" and "/primary/" in found.uri
        else Path("/tmp") / found.product
    )
    results = pipeline._resolve_bundle(
        DependencyBundle(name="precise", members=products, coherence=["AAA", "TTT", "PPP"]),
        {p: Dependency(spec=p) for p in products},
        date=datetime.datetime(2026, 8, 19),
        sink_id="local",
        preferences=spec.preferences,
        centers=None,
        download=True,
        force_download=False,
    )
    assert all(r.status == "downloaded" for r in results)
    assert all("/COD/FIN/" in r.remote_url for r in results)
    assert results[0].remote_url.startswith("https://primary/")
    assert results[1].remote_url.startswith("https://mirror/")
    assert all(
        call.kwargs["centers"] is None for call in pipeline._search_candidates.call_args_list
    )
    assert not any("/WUM/" in call.args[0].uri for call in pipeline._downloader.run.call_args_list)


def test_query_does_not_promote_protocol_over_preferences():
    def target(ac, protocol):
        return SimpleNamespace(
            product=SimpleNamespace(parameters=[SimpleNamespace(name="AAA", value=ac)]),
            server=SimpleNamespace(protocol=protocol),
        )

    https = target("WUM", "https")
    ftp = target("COD", "ftp")
    query = ProductQuery.__new__(ProductQuery)
    query._product = "ORBIT"
    query._date = datetime.datetime(2026, 8, 19)
    query._parameters = {}
    query._preferences = [
        p for p in DependencySpec.from_yaml(SPEC).preferences if p.parameter == "AAA"
    ]
    query._resolve_sources = lambda: ([], [])
    query._search_planner = MagicMock()
    query._wormhole = MagicMock()
    query._wormhole.search.return_value = [ftp, https]
    assert query._ranked_targets() == [https, ftp]
