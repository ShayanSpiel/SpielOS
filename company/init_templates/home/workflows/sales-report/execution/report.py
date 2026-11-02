"""Generic draft example: aggregate the explicit sales rows without external effects."""
import json,sys


def execute(inputs):
    return {'title':inputs['title'],'total':sum(inputs['sales']),'rows':len(inputs['sales'])}


if __name__=='__main__':
    print(json.dumps(execute(json.load(sys.stdin)),allow_nan=False))
