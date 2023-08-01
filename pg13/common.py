class CogMissing(Exception):

    def __init__(self, attempted, missing):
        super().__init__(
            f"Cog {attempted} depends on missing cog {missing} which was not loaded."
        )
