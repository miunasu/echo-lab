        """Command-line entry for minimal_pkg."""

        from __future__ import annotations


        def main() -> None:
            from minimal_pkg.core import hello
print(hello())


        if __name__ == "__main__":
            main()
