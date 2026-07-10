from src.adapters.crawling.normalizer_registry import InMemoryCrawlNormalizerRegistry
from src.adapters.crawling.normalizers.generic_stub_normalizer import GenericStubCrawlNormalizer
from src.adapters.crawling.plugin_registry import InMemoryCrawlerPluginRegistry
from src.adapters.crawling.plugin_runtime import CrawlerPluginRuntime
from src.adapters.observability.structured_lifecycle_telemetry_adapter import (
    StructuredLifecycleTelemetryAdapter,
)
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.application.ingestion.enrich_crawl_outcome import CrawlNormalizationService
from src.application.ingestion.normalize_records import NormalizeCrawlRecordsUseCase
from src.application.ingestion.track_lifecycle import JobLifecycleService
from src.application.use_cases.discover_jobs import DiscoverJobsUseCase
from src.ports.crawler_plugin_port import CrawlerPluginPort


def build_discovery_stack(
    repository,
    *,
    plugins: dict[str, CrawlerPluginPort],
    postings: InMemoryJobPostingAdapter | None = None,
    telemetry: StructuredLifecycleTelemetryAdapter | None = None,
) -> tuple[DiscoverJobsUseCase, InMemoryJobPostingAdapter]:
    lifecycle_telemetry = telemetry or StructuredLifecycleTelemetryAdapter()
    job_postings = postings or InMemoryJobPostingAdapter(telemetry=lifecycle_telemetry)
    normalizer = GenericStubCrawlNormalizer()
    normalizer_registry = InMemoryCrawlNormalizerRegistry(
        {plugin_id: normalizer for plugin_id in plugins}
    )
    normalize_use_case = NormalizeCrawlRecordsUseCase(job_posting_repository=job_postings)
    normalization_service = CrawlNormalizationService(
        repository=repository,
        normalizer_registry=normalizer_registry,
        normalize_use_case=normalize_use_case,
    )
    lifecycle_service = JobLifecycleService(repository=job_postings, telemetry=lifecycle_telemetry)
    discovery = DiscoverJobsUseCase(
        repository=repository,
        plugin_registry=InMemoryCrawlerPluginRegistry(plugins),
        runtime=CrawlerPluginRuntime(),
        normalization_service=normalization_service,
        lifecycle_service=lifecycle_service,
    )
    return discovery, job_postings
