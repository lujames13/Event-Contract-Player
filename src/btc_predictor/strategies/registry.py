
import importlib
import inspect
import sys
import logging
from pathlib import Path
from typing import List, Dict, Type
from btc_predictor.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

class StrategyRegistry:
    """自動發現並管理所有策略。"""

    def __init__(self) -> None:
        self._strategies: Dict[str, BaseStrategy] = {}

    def register(self, strategy: BaseStrategy) -> None:
        """手動註冊一個策略實例。"""
        if not isinstance(strategy, BaseStrategy):
            raise TypeError(f"Object {strategy} is not an instance of BaseStrategy")
        self._strategies[strategy.name] = strategy
        logger.info(f"Registered strategy: {strategy.name}")

    def discover(self, strategies_dir: Path, models_dir: Path) -> None:
        """
        掃描 strategies_dir 下的所有子目錄，找到繼承 BaseStrategy 的 class，
        並嘗試從 models_dir/{strategy_name}/ 載入對應的模型檔案。
        """
        strategies_dir = Path(strategies_dir)
        models_dir = Path(models_dir)

        if not strategies_dir.exists():
            logger.warning(f"Strategies directory not found: {strategies_dir}")
            return

        for item in strategies_dir.iterdir():
            if not item.is_dir():
                continue
            
            dir_name = item.name
            if dir_name.startswith("_") or dir_name == "__pycache__":
                continue
            
            strategy_file = item / "strategy.py"
            if not strategy_file.exists():
                logger.warning(f"Skipping {dir_name}: strategies.py not found")
                continue
            
            # Construct module path
            module_name = f"btc_predictor.strategies.{dir_name}.strategy"
            
            try:
                module = importlib.import_module(module_name)
            except ImportError as e:
                logger.error(f"Failed to import module {module_name}: {e}")
                continue
                
            # Find BaseStrategy subclass
            strategy_class: Type[BaseStrategy] = None
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                    strategy_class = obj
                    break
            
            if not strategy_class:
                logger.warning(f"No BaseStrategy subclass found in {module_name}")
                continue
                
            try:
                # Instantiate strategy using default constructor
                instance = strategy_class()
                
                # Check for models directory
                strat_models_dir = models_dir / instance.name
                if strat_models_dir.exists() and strat_models_dir.is_dir():
                    # Attempt to invoke load_models_from_dir if it exists (Convention)
                    if hasattr(instance, "load_models_from_dir"):
                         # Call the method I added to XGBoostDirectionStrategy
                        getattr(instance, "load_models_from_dir")(strat_models_dir)
                    else:
                        logger.debug(f"Strategy {instance.name} does not have load_models_from_dir method.")
                
                self.register(instance)

            except Exception as e:
                logger.error(f"Error loading strategy from {dir_name}: {e}")
                continue

    def get(self, name: str) -> BaseStrategy:
        """根據名稱取得策略實例。"""
        if name not in self._strategies:
            raise KeyError(f"Strategy '{name}' not found")
        return self._strategies[name]

    def list_names(self) -> List[str]:
        """列出所有已註冊的策略名稱。"""
        return list(self._strategies.keys())

    def list_strategies(self) -> List[BaseStrategy]:
        """列出所有已註冊的策略實例。"""
        return list(self._strategies.values())
