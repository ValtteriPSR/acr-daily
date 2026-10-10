import importlib.util
import tempfile
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('update_acr_catalogs', ROOT/'tools/update_acr_catalogs.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class CatalogUpdateTests(unittest.TestCase):
    def test_inventory_and_safe_comparison(self):
        cars="export const CARS = [\n" + '\n'.join(
            "{ id: 'carid%d', telemetry: 'tel%d', name: 'Car %d', cls: 'Rally2/R5', group: 'R' }," % (i,i,i)
            for i in range(15))
        old=mod.parse_inventory('cars.js', cars)
        assert len(old)==15
        new=mod.parse_inventory('cars.js',cars+"\n{ id: 'NewCar', telemetry: 'NewCar', name: 'New Car', cls: 'Rally4', group: 'R' },\n")
        add, removed, changed=mod.compare(old,new)
        self.assertEqual(add,['NewCar'])
        self.assertFalse(removed)
        self.assertFalse(changed)

    def test_unknown_or_small_catalog_rejected(self):
        with self.assertRaises(ValueError):
            mod.parse_inventory('cars.js', "export const CARS = [{ id:'x'}]")
        with self.assertRaises(ValueError):
            mod.parse_inventory('stages.js', 'MENU_NAMES = { GreeceS3: "Zeli" }')

    def test_apply_creates_backup_and_replaces(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            (base/'cars.js').write_text('before',encoding='utf-8')
            backup=mod.apply_updates({'cars.js':'after'},base)
            self.assertEqual((base/'cars.js').read_text(encoding='utf-8'),'after')
            self.assertEqual((backup/'cars.js').read_text(encoding='utf-8'),'before')

if __name__ == '__main__':unittest.main()
