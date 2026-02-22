"""
Tests for cogsol.core.loader utilities.
"""

from cogsol.content import BaseMetadataConfig, BaseRetrieval
from cogsol.core.loader import serialize_value


class TestSerializeValueTypeHandling:
    """Tests for serialize_value handling of type subclasses."""

    def test_metadata_config_with_name(self):
        """BaseMetadataConfig subclass with explicit name returns name."""

        class GenreMetadata(BaseMetadataConfig):
            name = "genre"

        assert serialize_value(GenreMetadata) == "genre"

    def test_metadata_config_without_name(self):
        """BaseMetadataConfig subclass without name returns __name__."""

        class GenreMetadata(BaseMetadataConfig):
            pass

        assert serialize_value(GenreMetadata) == "GenreMetadata"

    def test_metadata_config_list(self):
        """List of BaseMetadataConfig subclasses serializes each element."""

        class GenreMetadata(BaseMetadataConfig):
            name = "genre"

        class LanguageMetadata(BaseMetadataConfig):
            name = "language"

        result = serialize_value([GenreMetadata, LanguageMetadata])
        assert result == ["genre", "language"]

    def test_retrieval_still_works(self):
        """Existing BaseRetrieval handling is not broken."""

        class MyRetrieval(BaseRetrieval):
            name = "my_retrieval"

        assert serialize_value(MyRetrieval) == "my_retrieval"
