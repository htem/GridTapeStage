License
-----

Please note the [open-source license](LICENSE.md) before proceeding.
    

Files
-----

    docs/stage.md: description of stage
    docs/gridtape_stage.png: diagram of stage parts

    docs/protocol.md: description of command protocol and connection info
    docs/commands.md: description of commands, codes and options

    docs/tape_movement.png: diagram of stage movement states and transitions

    software/demo.py: demo python script
    software/temcagt: python control code

    firmware/temcagt_reel: arduino firmware

    docs/parts.xlsx: parts list for orings, fasteners, etc...
    docs/BOM_191002.xlsx: bill of materials including custom parts
    docs/pinouts.xlsx: drive electronics connector pinouts

    hardware/parts: design files for stage parts and assembly
    hardware/drawings: drawings of stage parts

    docs/assembly_instructions.pdf: electronics and hardware assembly
    docs/installation_instructions.pdf: installation instructions



Where to start
-----

It's recommended to read through the files in the order they are listed above.

Construction of a stage will require fabricating or purchasing parts found in
the main assembly hardware/parts/xy_v2.SLDASM. Refer to the BOM for a detailed
list of where to purchase and/or how to fabricate components.

See docs/stage.md for a description of the stage.

Extensions to the microcope column (the piezo chamber and reel housings)
should be fabricated, cleaned in a method compatible with a high vacuum system,
assembled with flanges and oring seals and attached to the microscope to
test for leaks. Then, electronics should be added and tape movement tested.
Finally, the piezos, tape channel, pickup rest and a test piece of tape should
be installed to test montaging of tape.
