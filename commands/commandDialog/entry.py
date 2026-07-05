import math
import traceback
import adsk.core, adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdDialog'
CMD_NAME = 'Bike Geo'
CMD_Description = 'Ajuste les user parameters du velo en temps reel'

# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# Configuration des user parameters pilotes par slider, groupes par categorie.
# kind='length' -> parametre en mm, stocke en interne en cm par Fusion.
# kind='angle'  -> parametre en degres, stocke en interne en radians par Fusion.
# min/max sont exprimes dans l'unite affichee (mm ou deg) : a ajuster selon ta geometrie.
PARAM_GROUPS = [
    ('Longueurs principales', [
        dict(name='Seat_tube_length', label='Longueur tube de selle', kind='length', min=400, max=650),
        dict(name='Head_tube_length', label='Longueur tube de direction', kind='length', min=80, max=220),
        dict(name='Top_tube_length', label='Longueur tube horizontal', kind='length', min=480, max=650),
        dict(name='Reach', label='Reach', kind='length', min=350, max=480),
        dict(name='Stack', label='Stack', kind='length', min=500, max=650),
        dict(name='chainstay_length', label='Longueur bases (chainstay)', kind='length', min=395, max=450),
        dict(name='top_tube_top_saddle', label='Tube horizontal - haut de selle', kind='length', min=0, max=100),
        dict(name='Seat_stays_center_seat_tube_distance', label='Haubans - axe tube de selle', kind='length', min=0, max=50),
    ]),
    ('Angles', [
        dict(name='seat_tube_angle', label='Angle tube de selle', kind='angle', min=68, max=76),
        dict(name='heat_tube_angle', label='Angle tube de direction', kind='angle', min=68, max=76),
    ]),
    ('Diametres de tubes', [
        dict(name='Top_tube_diam', label='Diam. tube horizontal', kind='length', min=20, max=40),
        dict(name='Down_tube_diam', label='Diam. tube diagonal', kind='length', min=25, max=50),
        dict(name='Seat_tube_diam', label='Diam. tube de selle', kind='length', min=25, max=35),
        dict(name='Head_tube_ID', label='Diam. int. tube de direction', kind='length', min=30, max=50),
        dict(name='Wheel_diameter_erd', label='Diametre jante (ERD)', kind='length', min=400, max=630),
    ]),
    ('Epaisseurs de tubes', [
        dict(name='Head_tube_thickness', label='Epaisseur tube direction', kind='length', min=0.5, max=3),
        dict(name='seat_tube_thickness', label='Epaisseur tube de selle', kind='length', min=0.5, max=3),
        dict(name='downtube_thickness', label='Epaisseur tube diagonal', kind='length', min=0.5, max=3),
        dict(name='top_tube_thickness', label='Epaisseur tube horizontal', kind='length', min=0.5, max=3),
    ]),
    ('Boitier de pedalier', [
        dict(name='Bottom_bracket_inner_diam', label='Diam. int. boitier', kind='length', min=30, max=45),
        dict(name='Bottom_bracket_outer_diam', label='Diam. ext. boitier', kind='length', min=35, max=50),
        dict(name='Bottom_bracket_width', label='Largeur boitier', kind='length', min=68, max=100),
        dict(name='Bottom_bracket_shell_cup_drive_side_thickness', label='Epaisseur coupelle cote transmission', kind='length', min=2, max=15),
        dict(name='Bottom_bracket_shell_cup_non_drive_side_thickness', label='Epaisseur coupelle cote oppose', kind='length', min=2, max=15),
        dict(name='cranck_arm_length', label='Longueur manivelle', kind='length', min=165, max=180),
    ]),
    ('Jeu de direction', [
        dict(name='Clearance_headtube_up', label='Jeu haut tube direction', kind='length', min=0, max=10),
        dict(name='Clearance_headtube_down', label='Jeu bas tube direction', kind='length', min=0, max=10),
        dict(name='Higher_headcup_height', label='Hauteur coupelle haute', kind='length', min=5, max=20),
        dict(name='lower_headcup_height', label='Hauteur coupelle basse', kind='length', min=5, max=20),
    ]),
    ('Fourche et roues', [
        dict(name='fork_offset', label='Offset fourche', kind='length', min=35, max=55),
        dict(name='axle_to_crown', label='Axe-couronne fourche', kind='length', min=350, max=450),
        dict(name='front_hub_spacing', label='Empattement moyeu avant', kind='length', min=74, max=110),
        dict(name='Rear_hub_spacing', label='Empattement moyeu arriere', kind='length', min=130, max=175),
    ]),
    ('Autres', [
        dict(name='Offset_seat_tube', label='Offset tube de selle', kind='length', min=0, max=30),
    ]),
]


# Executed when add-in is run.
def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)
    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()


def _slider_bounds(param_cfg: dict) -> tuple:
    """Convertit les bornes affichees (mm/deg) vers l'unite interne Fusion (cm/rad)."""
    if param_cfg['kind'] == 'angle':
        return math.radians(param_cfg['min']), math.radians(param_cfg['max'])
    return param_cfg['min'] / 10, param_cfg['max'] / 10


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')

    # Le design actif est recupere ici (a l'ouverture de la commande), pas a l'import du
    # module, pour toujours cibler le document reellement ouvert au moment de l'usage.
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        ui.messageBox('Aucune conception Fusion 360 active. Ouvre un fichier de conception avant de lancer Bike Geo.')
        return
    user_params = design.userParameters

    inputs = args.command.commandInputs

    for group_index, (group_name, param_list) in enumerate(PARAM_GROUPS):
        group = inputs.addGroupCommandInput(f'group_{group_index}', group_name)
        group.isExpanded = (group_index == 0)
        group_inputs = group.children

        for param_cfg in param_list:
            param = user_params.itemByName(param_cfg['name'])
            if param is None:
                futil.log(
                    f'{CMD_NAME}: user parameter "{param_cfg["name"]}" introuvable dans le document actif, slider ignore.',
                    adsk.core.LogLevels.WarningLogLevel
                )
                continue

            try:
                unit_label = 'deg' if param_cfg['kind'] == 'angle' else 'mm'
                min_v, max_v = _slider_bounds(param_cfg)
                value = param.value

                # Les bornes de PARAM_GROUPS sont des valeurs indicatives : si la valeur
                # actuelle du parametre dans le document est hors de cette plage, on elargit
                # la borne plutot que de planter (Fusion refuse un slider hors bornes).
                if value < min_v:
                    min_v = value
                elif value > max_v:
                    max_v = value

                slider = group_inputs.addFloatSliderCommandInput(
                    f'slider_{param_cfg["name"]}', param_cfg['label'], unit_label, min_v, max_v, False
                )
                slider.valueOne = value
            except:
                futil.log(
                    f'{CMD_NAME}: echec de creation du slider pour "{param_cfg["name"]}".\n{traceback.format_exc()}',
                    adsk.core.LogLevels.ErrorLogLevel
                )

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


def _apply_slider_values(inputs: adsk.core.CommandInputs):
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        return
    user_params = design.userParameters

    for _, param_list in PARAM_GROUPS:
        for param_cfg in param_list:
            slider: adsk.core.FloatSliderCommandInput = inputs.itemById(f'slider_{param_cfg["name"]}')
            if slider is None:
                continue
            param = user_params.itemByName(param_cfg['name'])
            if param is None:
                continue
            param.expression = slider.expressionOne


# This event handler is called when the user clicks the OK button in the command dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')
    _apply_slider_values(args.command.commandInputs)


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Preview Event')
    _apply_slider_values(args.command.commandInputs)


# This event handler is called when the user changes anything in the command dialog.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {args.input.id}')


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Destroy Event')

    global local_handlers
    local_handlers = []
