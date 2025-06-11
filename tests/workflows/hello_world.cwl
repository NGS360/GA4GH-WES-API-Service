cwlVersion: v1.0
class: Workflow

requirements:
  DockerRequirement:
    dockerPull: ubuntu:latest

inputs:
  name:
    type: string
    default: "World"

steps:
  say_hello:
    in:
      who: name
    run:
      class: CommandLineTool
      requirements:
        InlineJavascriptRequirement: {}
      baseCommand: echo
      arguments:
        - valueFrom: "Hello, $(inputs.who)!"
      stdout: hello.txt
      inputs:
        who:
          type: string
      outputs:
        output_file:
          type: stdout
    out: [output_file]

outputs:
  output_file:
    type: File
    outputSource: say_hello/output_file
