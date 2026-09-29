# TR-1um: Copyright 2025 OpenSUSI non-profit organaization 
#
# Original version was made by jun1okamura
# LICENSE: Apache License Version 2.0, January 2004,
#          http://www.apache.org/licenses/
# ----- ------ ----- ----- ------ ----- ----- ------ ----- 
#
import math
import pya
from .layers_def import *
from .rules_def  import *
from .util       import *

CSIO_GRID_UM = 0.05


def _snap_dimension_to_grid(value: float, minimum: float, maximum: float) -> float:
    """Clamp a CSIO dimension and snap all derived geometry to 50 nm."""
    value = min(max(value, minimum), maximum)
    snapped = math.floor(value / CSIO_GRID_UM + 0.5) * CSIO_GRID_UM
    return round(snapped, 9)

class cap(pya.PCellDeclarationHelper):

    def __init__(self):
        # Initialize super class.
        super(cap, self).__init__()
        #
        self.param("x", self.TypeDouble, "X", default=10.0, unit="um")
        self.param("y", self.TypeDouble, "Y", default=2.0,  unit="um")

    def display_text_impl(self):
        # Provide a descriptive text for the cell
        return "moscap(X=" + ('%3f' % self.x) + ",Y=" + ('%3f' % self.y) + ")"
    
    def coerce_parameters_impl(self):
        # Clamp and snap dimensions before constructing any CSIO geometry.
        rule = DR['AC.W1']
        self.x = _snap_dimension_to_grid(self.x, rule.min, rule.max)
        self.y = _snap_dimension_to_grid(self.y, rule.min, rule.max)

    def produce_impl(self):
        #
        draw_cap( self.cell, l=self.x, w=self.y )
